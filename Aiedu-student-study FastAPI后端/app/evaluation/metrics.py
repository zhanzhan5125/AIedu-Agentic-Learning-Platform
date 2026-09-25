from __future__ import annotations

import math
import random
from collections import Counter
from statistics import mean
from typing import Callable, Sequence


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 4)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 4)


def retrieval_case_metrics(
    ranked_keys: Sequence[str], relevance: dict[str, int],
) -> dict[str, float]:
    relevant = set(relevance)
    ranks = [index for index, key in enumerate(ranked_keys, 1) if key in relevant]
    first_rank = min(ranks) if ranks else None

    def recall(k: int) -> float:
        return len(relevant.intersection(ranked_keys[:k])) / max(1, len(relevant))

    dcg = sum((2 ** relevance.get(key, 0) - 1) / math.log2(index + 1)
              for index, key in enumerate(ranked_keys[:5], 1))
    ideal = sorted(relevance.values(), reverse=True)[:5]
    idcg = sum((2 ** score - 1) / math.log2(index + 1)
               for index, score in enumerate(ideal, 1))
    return {
        "recall_at_5": recall(5),
        "recall_at_6": recall(6),
        "mrr_at_10": 1 / first_rank if first_rank and first_rank <= 10 else 0.0,
        "ndcg_at_5": dcg / idcg if idcg else 0.0,
        "hit_at_1": float(bool(ranked_keys and ranked_keys[0] in relevant)),
    }


def average_metrics(rows: Sequence[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    return {key: round(mean(row[key] for row in rows), 4) for key in rows[0]}


def binary_metrics(expected: Sequence[bool], actual: Sequence[bool]) -> dict[str, float]:
    tp = sum(e and a for e, a in zip(expected, actual, strict=True))
    fp = sum(not e and a for e, a in zip(expected, actual, strict=True))
    fn = sum(e and not a for e, a in zip(expected, actual, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4)
        if precision + recall else 0.0,
    }


def multiclass_metrics(expected: Sequence[str], actual: Sequence[str]) -> dict[str, float]:
    labels = sorted(set(expected) | set(actual))
    scores = []
    for label in labels:
        values = binary_metrics(
            [value == label for value in expected],
            [value == label for value in actual],
        )
        scores.append(values["f1"])
    return {
        "accuracy": round(sum(e == a for e, a in zip(expected, actual, strict=True)) /
                          max(1, len(expected)), 4),
        "macro_f1": round(mean(scores), 4) if scores else 0.0,
    }


def paired_bootstrap_ci(
    baseline: Sequence[float], candidate: Sequence[float], *, seed: int = 42,
    samples: int = 1000, statistic: Callable[[Sequence[float]], float] = mean,
) -> dict[str, float]:
    if len(baseline) != len(candidate) or not baseline:
        return {"delta": 0.0, "ci95_low": 0.0, "ci95_high": 0.0}
    rng = random.Random(seed)
    deltas = []
    for _ in range(samples):
        indexes = [rng.randrange(len(baseline)) for _ in baseline]
        deltas.append(statistic([candidate[i] for i in indexes]) -
                      statistic([baseline[i] for i in indexes]))
    return {
        "delta": round(statistic(candidate) - statistic(baseline), 4),
        "ci95_low": percentile(deltas, 0.025),
        "ci95_high": percentile(deltas, 0.975),
    }


def issue_counts(values: Sequence[Sequence[str]]) -> dict[str, int]:
    return dict(Counter(issue for row in values for issue in row))
