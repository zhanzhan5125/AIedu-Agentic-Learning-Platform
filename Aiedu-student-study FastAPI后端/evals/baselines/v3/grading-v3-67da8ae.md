# AIedu Agent/RAG 正式评测报告

## 运行信息

- Git commit：`67da8ae5e0308e6e859dba6c8586c6066dd2a09e`
- 数据版本：`v3`
- LLM：`deepseek-v3.2`
- Embedding：`text-embedding-3-large`
- Reranker：`BAAI/bge-reranker-base`
- 运行时间：`2026-09-28T05:33:14.213438+00:00`

## 智能批阅消融评测

| 模式 | 归一化 MAE | 允许区间命中 | 边界合法 | 题目覆盖 | 证据支持 | 校验通过 |
| --- | --- | --- | --- | --- | --- | --- |
| raw | 0.0636 | 0.7333 | 1.0 | 1.0 | 1.0 | 1.0 |
| validate | 0.0636 | 0.7333 | 1.0 | 1.0 | 1.0 | 1.0 |
| reflect | 0.0503 | 0.8 | 1.0 | 1.0 | 1.0 | 1.0 |

- Reflection：`{'trigger_rate': 1.0, 'triggered_submissions': 20, 'triggered_answers': 60, 'validation_repair_success_rate': 0.0, 'validation_regression_rate': 0.0, 'score_change_rate': 0.1667, 'score_improvement_rate': 0.1167, 'score_regression_rate': 0.05, 'accepted_range_repairs': 5, 'accepted_range_regressions': 1, 'semantic_repair_rate': 0.3125, 'review_improvements': 6, 'review_regressions': 5, 'mae_delta': -0.0133, 'retain_conditional_reflection': True}`
- 性能与成本：`{'raw_latency_p50_ms': 16502.8285, 'raw_latency_p95_ms': 22748.4959, 'reflection_latency_p50_ms': 30710.2495, 'total_latency_p50_ms': 49360.0635, 'total_latency_p95_ms': 64292.2717, 'prompt_tokens': 99485, 'completion_tokens': 39197, 'estimated_cost_usd': None, 'average_estimated_cost_usd': None}`
- Reflection 后仍失败案例：无

## 使用限制

- 所有简历数字必须来自本报告对应的 JSON 原始结果。
- RAG 端到端 Judge 结果在人工盲审完成前只能作为辅助指标。
- 负向或无提升结果必须保留，不得选择性删除失败案例。
