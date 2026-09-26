# AIedu Agent/RAG 正式评测报告

## 运行信息

- Git commit：`7d6725801067e4db4c7e7bef1dafb2dd312394f6`
- 数据版本：`v1`
- LLM：`deepseek-v3.2`
- Embedding：`text-embedding-3-large`
- Reranker：`BAAI/bge-reranker-base`
- 运行时间：`2026-09-26T01:53:54.098538+00:00`

## 结构化意图路由评测

| 模式 | Accuracy | Macro-F1 | 委派 Precision | 委派 Recall | 委派 F1 | 工具 Exact Match |
| --- | --- | --- | --- | --- | --- | --- |
| rules | 0.675 | 0.6043 | 1.0 | 0.6429 | 0.7826 | 0.7 |
| model | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9 |

- 稳定性与性能：`{'structured_output_failure_rate': 0.0, 'fallback_rate': 0.0, 'repeat_consistency_rate': 1.0, 'latency_p50_ms': 3102.9685, 'latency_p95_ms': 4107.8765, 'prompt_tokens': 35769, 'completion_tokens': 3398}`
- 模型路由失败案例：routing-018, routing-021, routing-033, routing-036

## 使用限制

- 所有简历数字必须来自本报告对应的 JSON 原始结果。
- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。
- 负向或无提升结果必须保留，不得选择性删除失败案例。
