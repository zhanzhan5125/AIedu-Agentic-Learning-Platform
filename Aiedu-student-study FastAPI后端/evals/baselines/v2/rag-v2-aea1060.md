# AIedu Agent/RAG 正式评测报告

## 运行信息

- Git commit：`aea1060936ecabaa6fccf55bae2f2fea5fc7fd40`
- 数据版本：`v2`
- LLM：`deepseek-v3.2`
- Embedding：`text-embedding-3-large`
- Reranker：`BAAI/bge-reranker-base`
- 运行时间：`2026-09-26T03:06:45.596111+00:00`

## RAG 消融评测

| 模式 | Recall@5 | Recall@6 | MRR@10 | nDCG@5 | Hit@1 | p50(ms) | p95(ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bm25 | 0.6771 | 0.7552 | 0.5956 | 0.568 | 0.4062 | 303.5955 | 380.6424 |
| dense | 0.9271 | 0.9271 | 0.5854 | 0.6582 | 0.3125 | 862.2125 | 1350.698 |
| hybrid | 0.8438 | 0.8438 | 0.6977 | 0.7033 | 0.5 | 1180.243 | 1583.1619 |
| hybrid_rerank | 0.8906 | 0.8906 | 0.7776 | 0.7814 | 0.6562 | 6825.674 | 7395.399 |

- Rerank nDCG@5 差值：`{'delta': 0.078, 'ci95_low': -0.0014, 'ci95_high': 0.1682}`
- Rerank Recall@5 差值：`{'delta': 0.0469, 'ci95_low': 0.0, 'ci95_high': 0.125}`
- Rerank warm p95：5851.1038 ms
- Reranker 实际设备：`cpu`
- 是否推荐默认启用：否
- 重排退化案例：rag-005, rag-009, rag-014, rag-019, rag-026
- 端到端盲评：`{'hybrid': 1, 'hybrid_rerank': 0, 'tie': 11}`；状态：pending_human_audit

## 使用限制

- 所有简历数字必须来自本报告对应的 JSON 原始结果。
- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。
- 负向或无提升结果必须保留，不得选择性删除失败案例。
