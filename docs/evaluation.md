# AIedu 可复现 Agent/RAG 评测

项目提供三组离线、只读评测：RAG 检索消融、智能批阅 Reflection 消融、学生问答意图路由对比。评测不会发布作业、修改成绩、更新画像或创建 Agent Run。

## 数据状态

`Aiedu-student-study FastAPI后端/evals/v1` 包含三组已审核基线；`evals/v2` 保留同样的问题与路由/批阅标签，并将 RAG 证据映射到结构化重切分后的 597 个有效块：

| 数据集 | 数量 | 当前状态 |
|---|---:|---|
| RAG | 40 条，其中 32 条可回答、8 条不可回答 | 已审核并批准 |
| 智能批阅 | 10 份合成提交、30 条答案 | 已审核并批准 |
| 意图路由 | 40 条，其中 10 条重复运行 | 已审核并批准 |

三组数据当前均使用 `approved: true`。审核记录见 [v1 评测集审核记录](evaluation-dataset-audit-v1.md)。正式命令仍会拒绝任何后续新增但未审核的数据，防止把机器生成标签包装成金标准。

人工审核时需要：

1. RAG：确认问题能否由课程资料回答、相关 `resource_title + content_hash` 和 1–3 级相关性。
2. 批阅：确认参考答案、Rubric、`gold_score`、允许分数区间和是否应人工复核。
3. 路由：确认意图、学习助手委派、课程检索、网页检索和身份请求标签。
4. 确认后逐条把 `approved` 改为 `true`，不得批量确认未阅读样本。

生成包含课程切片原文的审核清单：

```powershell
uv run python -m scripts.export_eval_review --dataset-version v1 --offering-id 2
```

输出默认位于 `evals/results/review_v1.md`，只作为本地审核辅助，不会自动修改金标准文件。

## 运行

```powershell
cd "Aiedu-student-study FastAPI后端"
uv sync --extra dev --extra reranker

# 正式评测：要求全部人工确认，并要求 reranker 真正执行
uv run python -m scripts.evaluate_agents --suite all --dataset-version v2 --offering-id 2

# 候选数据预跑：结果带醒目的“非正式”水印，不能写入简历
uv run python -m scripts.evaluate_agents --suite routing --draft
uv run python -m scripts.evaluate_agents --suite rag --draft --allow-reranker-fallback --skip-end-to-end

# 只验证执行链路，不形成指标结论
uv run python -m scripts.evaluate_agents --suite rag --draft --max-cases 3 --skip-end-to-end
```

可选成本参数：

```powershell
uv run python -m scripts.evaluate_agents --suite grading `
  --input-cost-per-million <输入价格> `
  --output-cost-per-million <输出价格>
```

每次运行在 `evals/results` 生成 JSON 原始结果和 Markdown 报告。结果记录 Git commit、数据版本、模型、Embedding、reranker、分阶段耗时、Token、逐样本输出和失败案例。

## 指标与决策规则

RAG 对比 BM25、Dense、RRF、RRF+Rerank，报告 Recall@5/6、MRR@10、nDCG@5、Hit@1 和 p50/p95。只有当 Rerank 的 nDCG@5 至少提升 0.03、Recall@5 不下降超过 0.01、增量 p95 不超过 500ms 时，报告才推荐默认启用。

批阅复用同一份 Raw 输出，对比 Raw、确定性 Validate 和一次 Reflect，报告归一化 MAE、人工允许区间命中率、证据支持率、结构合法率、人工复核 F1、修复率、回归率与成本。

路由对比规则 fallback 和 Structured Outputs 模型路由，报告 Accuracy、Macro-F1、委派 Precision/Recall/F1、工具 Exact Match、fallback 率、一致率和延迟。

## 简历结论规则

commit `7d67258` 的完整 v1 正式评测见 [v1 正式评测结果](evaluation-results-v1.md)；commit `aea1060` 的结构化切片 RAG 复测见 [RAG v2 正式评测结果](evaluation-results-v2.md)。正式报告只能引用基线 JSON 中能够重新计算的指标。Rerank 虽改善 v2 排序指标，但仍未达到延迟门槛；Reflection 也未产生额外收益，报告保留这些负向结论。
