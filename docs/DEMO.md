# 8 分钟演示脚本

## 1. 教师课程助手与课程路线（2 分钟）

1. 上传一份带章节标题的 PDF、一份 DOCX 教学大纲和一份 PPTX 课件。
2. 在资料页确认状态为“已完成索引”，打开课程多智能体工作台。
3. 点击“从已索引资料生成”，展示路线左侧章节、右侧关系图。
4. 点击节点，展示资料名以及页码/幻灯片号；修改节点名称或顺序后保存。
5. 发布路线，切换学生端展示同一已发布版本。

讲解重点：路线不是模型直接写入知识点；它先成为带 evidence 的草稿，教师发布后才同步。

## 2. 教师出题/批阅智能体（2 分钟）

1. 输入“二叉树、递归”，3 道简答题，难度 2。
2. 展示生成题目、参考答案、Rubric 和引用数量。
3. 展开运行轨迹，指出 `make_plan`、`execute_tools`、`validate_result` 和最多一次 `reflect_once`。
4. 打开父 Run 的 `delegated_run_ids`，说明出题智能体按需委派了教师课程助手。
5. 批阅场景展示每题分数边界检查和 `needs_review`；强调教师确认前不更新最终成绩与画像。

## 3. 学生问答智能体（2 分钟）

1. 提问普通课程问题，展示课程引用；说明没有调用个人画像。
2. 提问“结合我的情况，我应该如何复习？”，展示学生学习助手子 Run。
3. 复制一条开放作业题提问，展示“不能直接给出答案”的分步引导。
4. 提问课程资料未覆盖的问题，展示证据不足说明；配置网页密钥时可演示只读网页证据。

## 4. 学情与可靠性（2 分钟）

1. 打开“我的学情”，解释“画像覆盖率 5/8”，而非含义模糊的“0 证据不足”。
2. 点击证据数，展示来源、时间、置信度与还差几条。
3. 演示按钮随状态变为薄弱点巩固、诊断练习或综合巩固。
4. 打开 Network/后端日志，说明未读汇总正常只在登录/切课/WebSocket 事件触发；断线后才 60 秒轮询。

## 验收查询

```sql
SELECT id, agent_name, task_type, parent_run_id, reflection_count, status, latency_ms
FROM agent_runs ORDER BY id DESC LIMIT 20;

SELECT run_id, position, node_name, step_type, tool_name, duration_ms
FROM agent_run_steps ORDER BY id DESC LIMIT 50;
```
