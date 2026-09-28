# AIedu Agent/RAG 正式评测报告

## 运行信息

- Git commit：`61241a5d3c0a857885a75208ffda2bb543bf8c0d`
- 数据版本：`v2`
- LLM：`deepseek-v3.2`
- Embedding：`text-embedding-3-large`
- Reranker：`BAAI/bge-reranker-base`
- 运行时间：`2026-09-28T06:13:44.101436+00:00`

## RAG 消融评测

| 模式 | Recall@5 | Recall@6 | MRR@10 | nDCG@5 | Hit@1 | p50(ms) | p95(ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | 0.6771 | 0.7552 | 0.5956 | 0.568 | 0.4062 | 357.986 | 531.8588 |
| dense | 0.9271 | 0.9271 | 0.5854 | 0.6582 | 0.3125 | 808.4825 | 1435.2543 |
| dense_rerank | 0.8958 | 0.8958 | 0.7966 | 0.7946 | 0.6875 | 6854.613 | 8603.5479 |
| hybrid | 0.8438 | 0.8438 | 0.6977 | 0.7033 | 0.5 | 1190.2685 | 2201.8193 |
| hybrid_rerank | 0.8906 | 0.8906 | 0.7776 | 0.7814 | 0.6562 | 7321.4665 | 9167.2857 |

- Rerank nDCG@5 差值：`{'delta': 0.078, 'ci95_low': -0.0014, 'ci95_high': 0.1682}`
- Rerank Recall@5 差值：`{'delta': 0.0469, 'ci95_low': 0.0, 'ci95_high': 0.125}`
- Dense 加 Rerank：`{'recall_at_5': {'delta': -0.0312, 'ci95_low': -0.1094, 'ci95_high': 0.0312}, 'ndcg_at_5': {'delta': 0.1365, 'ci95_low': 0.0465, 'ci95_high': 0.2268}, 'hit_at_1': {'delta': 0.375, 'ci95_low': 0.2188, 'ci95_high': 0.5312}}`
- Dense+Rerank 对 Hybrid+Rerank：`{'recall_at_5': {'delta': -0.0052, 'ci95_low': -0.0469, 'ci95_high': 0.0312}, 'ndcg_at_5': {'delta': -0.0133, 'ci95_low': -0.047, 'ci95_high': 0.0152}, 'hit_at_1': {'delta': -0.0312, 'ci95_low': -0.0938, 'ci95_high': 0.0}}`
- Rerank warm p95：7446.3465 ms
- Reranker 实际设备：`cpu`
- 是否推荐默认启用：否
- 重排退化案例：rag-005, rag-009, rag-014, rag-019, rag-026
- Dense 重排退化案例：rag-003, rag-008, rag-010, rag-014, rag-019, rag-026
- 端到端盲评：`{'hybrid': 0, 'hybrid_rerank': 0, 'tie': 0}`；状态：not_run

## 使用限制

- 所有简历数字必须来自本报告对应的 JSON 原始结果。
- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。
- 负向或无提升结果必须保留，不得选择性删除失败案例。
