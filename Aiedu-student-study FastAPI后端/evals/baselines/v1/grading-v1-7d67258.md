# AIedu Agent/RAG 正式评测报告

## 运行信息

- Git commit：`7d6725801067e4db4c7e7bef1dafb2dd312394f6`
- 数据版本：`v1`
- LLM：`deepseek-v3.2`
- Embedding：`text-embedding-3-large`
- Reranker：`BAAI/bge-reranker-base`
- 运行时间：`2026-09-26T01:50:53.843755+00:00`

## 智能批阅消融评测

| 模式 | 归一化 MAE | 允许区间命中 | 边界合法 | 题目覆盖 | 证据支持 | 校验通过 |
| --- | --- | --- | --- | --- | --- | --- |
| raw | 0.0389 | 0.8667 | 1.0 | 1.0 | 1.0 | 1.0 |
| validate | 0.0389 | 0.8667 | 1.0 | 1.0 | 1.0 | 1.0 |
| reflect | 0.0389 | 0.8667 | 1.0 | 1.0 | 1.0 | 1.0 |

- Reflection：`{'trigger_rate': 0.0, 'repair_success_rate': 0.0, 'regression_rate': 0.0, 'retain_conditional_reflection': False}`
- 性能与成本：`{'raw_latency_p50_ms': 11959.2525, 'raw_latency_p95_ms': 14241.7622, 'reflection_latency_p50_ms': 0.0845, 'total_latency_p50_ms': 11959.6415, 'total_latency_p95_ms': 14241.9895, 'prompt_tokens': 15351, 'completion_tokens': 4711, 'estimated_cost_usd': None, 'average_estimated_cost_usd': None}`
- Reflection 后仍失败案例：无

## 使用限制

- 所有简历数字必须来自本报告对应的 JSON 原始结果。
- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。
- 负向或无提升结果必须保留，不得选择性删除失败案例。
