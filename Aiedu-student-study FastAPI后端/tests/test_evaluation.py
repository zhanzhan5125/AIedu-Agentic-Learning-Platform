from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.evaluation.metrics import (
    binary_metrics, multiclass_metrics, paired_bootstrap_ci, percentile,
    retrieval_case_metrics,
)
from app.evaluation import runner
from app.evaluation.schemas import (
    GradingEvalDataset, RAGEvalDataset, RoutingEvalDataset, assert_official_dataset,
)
from app.integrations import rag


def test_retrieval_metrics_have_known_values():
    values = retrieval_case_metrics(
        ["irrelevant", "gold-a", "gold-b"], {"gold-a": 3, "gold-b": 1},
    )
    assert values["recall_at_5"] == 1
    assert values["mrr_at_10"] == 0.5
    assert values["hit_at_1"] == 0
    assert 0 < values["ndcg_at_5"] < 1
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_classification_and_bootstrap_metrics_are_deterministic():
    assert binary_metrics([True, True, False], [True, False, True]) == {
        "precision": 0.5, "recall": 0.5, "f1": 0.5,
    }
    values = multiclass_metrics(["a", "b", "b"], ["a", "a", "b"])
    assert values["accuracy"] == 0.6667
    first = paired_bootstrap_ci([0, 0, 1], [1, 0, 1], seed=7)
    second = paired_bootstrap_ci([0, 0, 1], [1, 0, 1], seed=7)
    assert first == second
    assert first["delta"] == 0.3333
    assert runner._routing_signature({
        "intent": "course_qa", "delegate_student_learning_assistant": False,
        "search_course_materials": True, "search_web": False,
        "identity_request": False, "rationale": "第一次理由",
    }) == runner._routing_signature({
        "intent": "course_qa", "delegate_student_learning_assistant": False,
        "search_course_materials": True, "search_web": False,
        "identity_request": False, "rationale": "不同措辞但相同决策",
    })


def test_explicit_retrieval_modes_use_distinct_paths(monkeypatch):
    dense = [{"chunk_id": 1, "resource_id": 1, "position": 1,
              "retrieval_source": "dense", "score": 0.8, "text": "dense"}]
    lexical = [{"chunk_id": 2, "resource_id": 1, "position": 2,
                "retrieval_source": "bm25", "score": 4.0, "text": "lexical"}]
    monkeypatch.setattr(rag, "_dense_search", lambda *_: list(dense))
    monkeypatch.setattr(rag, "_bm25_search", lambda *_: list(lexical))
    monkeypatch.setattr(rag, "_attach_context_windows", lambda db, values: values)
    monkeypatch.setattr(rag, "_rerank_with_diagnostics", lambda query, values, required=False: (
        list(reversed(values)), {
            "reranker_requested": True, "reranker_applied": True,
            "reranker_model": "test", "reranker_device": "cpu", "reranked_candidates": len(values),
        },
    ))
    db = SimpleNamespace()

    assert rag.retrieve_course(2, "q", mode="bm25", db=db).results[0]["chunk_id"] == 2
    assert rag.retrieve_course(2, "q", mode="dense", db=db).results[0]["chunk_id"] == 1
    hybrid = rag.retrieve_course(2, "q", mode="hybrid", db=db)
    assert {item["chunk_id"] for item in hybrid.results} == {1, 2}
    reranked = rag.retrieve_course(
        2, "q", mode="hybrid_rerank", db=db, require_reranker=True,
    )
    assert reranked.diagnostics["reranker_applied"] is True
    assert reranked.results[0]["chunk_id"] != hybrid.results[0]["chunk_id"]


def test_required_reranker_never_silently_falls_back(monkeypatch):
    rag._load_reranker.cache_clear()
    monkeypatch.setattr(rag, "_load_reranker", lambda: None)
    with pytest.raises(RuntimeError, match="Reranker 未加载"):
        rag._rerank_with_diagnostics("q", [{"text": "chunk"}], required=True)


def test_retrieval_variants_share_dense_and_bm25_work(monkeypatch):
    calls = {"dense": 0, "bm25": 0, "rerank": 0}

    def dense(*_):
        calls["dense"] += 1
        return [{"chunk_id": 1, "resource_id": 1, "position": 1,
                 "retrieval_source": "dense", "score": 0.8, "text": "dense"}]

    def bm25(*_):
        calls["bm25"] += 1
        return [{"chunk_id": 2, "resource_id": 1, "position": 2,
                 "retrieval_source": "bm25", "score": 2.0, "text": "lexical"}]

    def rerank(query, values, required=False):
        calls["rerank"] += 1
        return values, {"reranker_applied": True, "reranker_device": "cpu"}

    monkeypatch.setattr(rag, "_dense_search", dense)
    monkeypatch.setattr(rag, "_bm25_search", bm25)
    monkeypatch.setattr(rag, "_rerank_with_diagnostics", rerank)
    variants = rag.retrieve_course_variants(2, "q", db=SimpleNamespace())
    assert set(variants) == {"bm25", "dense", "hybrid", "hybrid_rerank"}
    assert calls == {"dense": 1, "bm25": 1, "rerank": 1}


def test_grading_ablation_reuses_one_raw_model_output(monkeypatch):
    dataset = GradingEvalDataset.model_validate({
        "version": "test", "contains_personal_data": False,
        "submissions": [{
            "id": "grading-001", "source": "synthetic", "approved": True,
            "answers": [{
                "id": "a1", "kind": "short_answer", "prompt": "题目",
                "reference_answer": "答案", "rubric": ["要点"], "max_score": 10,
                "student_answer": "答案", "gold_score": 10,
                "accepted_min": 9, "accepted_max": 10,
            }],
        }],
    })
    calls = {"model": 0, "reflect": 0}
    raw = {
        "items": [{"answer_id": 1, "score": 10, "max_score": 10,
                   "rubric": ["要点"], "comment": "正确", "error_type": None,
                   "evidence_excerpt": "答案", "confidence": 95}],
        "total_score": 10, "overall_comment": "正确", "confidence": 95,
        "needs_review": False, "review_reason": None,
    }

    def model(_state):
        calls["model"] += 1
        return raw, {"token_usage": {"prompt": 10, "completion": 5, "total": 15}}

    validation = SimpleNamespace(model_dump=lambda: {
        "valid": True, "issues": [], "evidence_sufficient": True,
        "requires_human_review": True,
    })

    def reflect(state):
        calls["reflect"] += 1
        return {**state, "draft": state["draft"], "validation": validation.model_dump()}

    monkeypatch.setattr(runner.workflows, "_model_grading", model)
    monkeypatch.setattr(runner.workflows, "_validate", lambda _state: validation)
    monkeypatch.setattr(runner.workflows, "reflect_once", reflect)
    result = runner.run_grading_suite(dataset)
    assert calls == {"model": 1, "reflect": 1}
    assert result["summary"]["raw"]["normalized_mae"] == 0
    assert result["cases"][0]["reflect"]["result"]["needs_review"] is False


def test_unapproved_or_privacy_shaped_dataset_is_rejected():
    payload = {
        "version": "v1", "offering_id": 2, "contains_personal_data": False,
        "cases": [{
            "id": "rag-001", "category": "unanswerable", "query": "未知问题",
            "answerable": False, "relevant_chunks": [], "approved": False,
        }],
    }
    dataset = RAGEvalDataset.model_validate(payload)
    with pytest.raises(ValueError, match="未人工确认"):
        assert_official_dataset(dataset, "rag")
    payload["student_name"] = "不应出现"
    with pytest.raises(ValidationError):
        RAGEvalDataset.model_validate(payload)


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_shipped_datasets_are_approved_and_balanced(version):
    root = Path(__file__).parents[1] / "evals" / version
    rag_dataset = runner.load_dataset(
        root / "rag.json", RAGEvalDataset, official=True, suite="rag",
    )
    grading_dataset = runner.load_dataset(
        root / "grading.json", GradingEvalDataset, official=True, suite="grading",
    )
    routing_dataset = runner.load_dataset(
        root / "routing.json", RoutingEvalDataset, official=True, suite="routing",
    )

    assert len(rag_dataset.cases) == 40
    assert all(len(case.relevant_chunks) >= 2 for case in rag_dataset.cases
               if case.category == "multi_evidence")
    assert sum(case.end_to_end for case in rag_dataset.cases) == 12
    assert sum(case.end_to_end and not case.answerable for case in rag_dataset.cases) == 4
    assert sum(len(case.answers) for case in grading_dataset.submissions) == 30
    assert sum(answer.should_review for case in grading_dataset.submissions
               for answer in case.answers) == 3
    repeated_categories = {case.category for case in routing_dataset.cases if case.repeat}
    assert sum(case.repeat for case in routing_dataset.cases) == 10
    assert repeated_categories >= {
        "course_qa", "resource_lookup", "personalized", "identity", "current_web",
        "chitchat", "followup",
    }
