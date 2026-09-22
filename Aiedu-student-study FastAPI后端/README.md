# AIedu FastAPI 后端

这是与旧 Spring Boot 服务并行运行的新后端。默认端口为 `9091`，不会修改旧业务表；新表统一使用 `app_` 前缀或新的明确表名。

## 本地开发

开发阶段只在 Docker 中运行 MySQL、Redis、Qdrant 和 RocketMQ；FastAPI 与 Worker 在宿主机运行，以便使用热重载。先在项目根目录启动中间件：

```powershell
docker compose up -d
```

然后进入本目录。复制 `.env.example` 后，把其中 MySQL、Redis 密码改成根目录 `.env` 中对应的值（不要提交生成的 `.env`）：

```powershell
copy .env.example .env
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 9091 --reload
```

另开终端启动异步 Worker：

```powershell
uv run python -m app.worker
```

本地默认连接 MySQL `localhost:3307`、Redis `localhost:6379`、Qdrant `localhost:6333`、MinIO `localhost:9000` 和 RocketMQ Proxy `localhost:8081`。课程资料原文件存入 MinIO，Worker 解析 PDF/DOCX/PPTX 后将课程隔离的切片向量写入 Qdrant；开发/测试也可将 `AIEDU_OBJECT_STORAGE_BACKEND` 设为 `local`。如需暂时绕过 RocketMQ，可设置 `AIEDU_ENABLE_MQ=false`，Worker 会直接消费数据库 Outbox。接口文档地址为 `http://localhost:9091/docs`。

完整应用容器仅用于 CI/验收，不用于日常开发：

```powershell
docker compose --profile container-app up -d --build
```

## 数据迁移

1. 先对现有 MySQL 做完整备份，不得直接在唯一生产库试跑。
2. 将 `AIEDU_DATABASE_URL` 指向包含旧表的备份副本。
3. 执行 `uv run alembic upgrade head` 创建或升级 v2 表。
4. 执行 `uv run python -m scripts.migrate_legacy_teaching_sections`，为旧开课表增加教学班编号和名称；已有开课默认迁移为 `01 / 教学班01`。
5. 执行 `uv run python -m scripts.migrate_legacy`。脚本可重复执行，迁移用户、课程、开课、选课、作业、题目、提交、答案和成绩。
6. 核对输出中的各实体数量、孤儿记录和歧义答案数。旧答案表没有作业编号；同一题目被多份作业复用时会计入 `ambiguous_answers`，必须人工抽样核对。至少在生产备份副本上完整演练两次，未通过前不得切流。

开课实例按“课程 + 学年 + 学期 + 教学班编号”唯一。教师可为同一课程在同一学期开设 `01`、`02` 等多个教学班；学生仍以唯一学号直接加入具体开课实例，不建立行政班模型。

## 已有接口

- 认证：登录、刷新、退出、当前用户、修改密码；旧 MD5 登录后自动升级 Argon2id。
- 管理员：用户分页、新建、重置密码；课程分页、新建、约束删除。
- 教师/学生：开课、课程、作业草稿、发布、作答、提交、人工批阅、未提交名单、成绩 CSV。
- AI：批阅、总结、出题、RAG 任务，任务查询和带归属校验的 WebSocket 进度。
- 课程问答会话：创建、按教学班分页/列出、读取有序消息、追加消息和归档；会话及消息持久化到 MySQL。
- 多智能体：课程作业草稿、个人复习题、Agent Run/步骤审计，以及旧 AI Job 接口的兼容执行。
- 学情：课程知识点、题目映射、学习证据、个人掌握度、班级洞察和作业易错分析。
- 课程资料：教师上传、异步解析/索引、课程成员预览下载、重新索引和逻辑删除。
- 问答导师：RAG 引用、开放作业相似度检测和苏格拉底式辅导策略。
- 课程消息：教师公告、同班一对一私聊、跨课程聚合、已读状态和 WebSocket 增量推送。
- 公共能力：提示词版本、个人通知、受权限保护的图片/PDF 上传下载。

## 多智能体边界

- LangGraph 节点只生成结构化建议；发布作业和确认成绩仍由教师接口完成。
- 掌握度、活跃度、平均分和易错率由确定性服务计算，LLM 不直接计算业务指标。
- `agent_runs` 和 `agent_run_steps` 保存模型版本、工具摘要、耗时与结果，不保存模型隐式思维链。
- 新事件继续使用 Transactional Outbox；Redis 只用于会话、限流、锁、缓存和实时分发，不作为最终业务存储。

## 验证

```powershell
uv run pytest
```

测试覆盖统一错误结构、RBAC、MD5 升级、数据库分页、重复发布、Outbox 和 AI 任务幂等。
