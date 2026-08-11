# Misaka 知识库（RAG）功能审查报告

## 1. 审查摘要

审查日期：2026-08-11
审查分支：`codex/fix-issue-2-marketplace`
基线提交：`940132eadc2a707886c78f0e30d7e564d55ac493`（`fix: make environment setup reliable (#15)`）
运行环境：Windows / Python 3.13.9 / Flet 0.80.5
审查方式：源码走查、架构与需求对照、静态检查、现有测试、故障注入、并发复现、真实文件解析、现有 PyInstaller 产物检查。

### 总体结论

知识库模块的分层和基础主流程已经成形：知识库 CRUD、文档上传、解析、分块、嵌入、SQLite/SeekDB 向量后端、混合检索、聊天上下文注入和管理 UI 均已接通。在当前源码开发环境中，已有自动化测试和本次构造的正常路径均可通过。

但是，当前版本不能判定为“可稳定正常使用”或“发布就绪”。失败重建会先销毁旧索引且保留虚假统计；处理中的文档可被删除并留下孤儿向量；远程向量清理失败仍会删除本地记录；检索配置有部分完全不生效；RRF 会把同一分块作为两个结果；打包配置又排除了默认 BM25 必需的 NumPy，现有冻结产物中也没有 sqlite-vec 的 `vec0.dll`。这些问题会导致数据丢失、索引与界面状态不一致、检索失效或发布版知识库不可用。

本次共记录 20 项问题：

| 等级 | 数量 | 含义 |
|---|---:|---|
| P0 | 2 | 发布阻断：可造成已建索引丢失，或冻结发布版核心能力不可用 |
| P1 | 7 | 严重：数据一致性、后端切换、检索正确性或失败可见性问题 |
| P2 | 8 | 中等：格式兼容、性能、安全边界、验证和确定性问题 |
| P3 | 3 | 较低：规模化、资源管理和长期维护风险 |

建议在修复 P0 与 P1、增加对应回归测试，并完成冻结版 smoke test 和真实远程 SeekDB/模型端点 E2E 后，再将该功能视为可发布。

## 2. 审查范围与架构

### 2.1 覆盖范围

- `misaka/services/knowledge/`：知识库、文档、RAG 编排器及 LangChain/SeekDB 适配器。
- `misaka/ui/knowledge/`：知识库列表、详情、创建编辑、文档上传/查看/重处理、聊天选择器。
- `misaka/services/chat/preprocessors.py`：聊天发送前的 RAG 检索和上下文注入。
- `misaka/ui/chat/components/message_input.py`：知识库选择入口。
- `misaka/ui/settings/components/vector_backend_panel.py` 与 `misaka/main.py`：向量后端配置及重建状态。
- `misaka/db/`：知识库、文档、分块、设置的模型、迁移和 CRUD。
- `misaka.spec`、`pyproject.toml`：打包与运行依赖。
- `tests/integration/test_knowledge_backend_flow.py`、知识库相关单元测试和全量测试。
- `docs/demand/KNOWLEDGE_BASE_DESIGN.md`、`docs/demand/RAG_BEST_PRACTICES.md`、`docs/plans/KNOWLEDGE_BASE_SEEKDB_TODO.md`：需求与实现对照。

审查期间工作树存在由其他任务产生的 Marketplace/MCP/README/CI 等未提交修改；本报告未修改这些文件。知识库目录和数据库相关目录在审查期间未发现并发改动。`misaka/main.py` 的并发修改仅涉及 MCP Marketplace 服务注入，不改变本报告引用的向量后端判断逻辑。

### 2.2 实际数据流

```text
UI 上传文件
  -> DocumentService 校验、计算 SHA-256、复制到 ~/.misaka/knowledge_bases/<kb>/
  -> RAGOrchestrator 解析 -> 分块 -> 嵌入 -> 写向量后端
  -> DocumentService 写 kb_chunks、更新 kb_documents 和知识库统计

聊天选择知识库
  -> RAGPreprocessor 构造各知识库嵌入配置
  -> RAGOrchestrator 对每个知识库嵌入查询
  -> 向量检索 + BM25 -> RRF -> 可选 reranker
  -> format_context() 拼接 XML 风格上下文 -> 发送给模型
```

主要架构优点：

- 解析器、分块器、嵌入器、向量存储、检索器、重排器有抽象接口，SQLite 与 SeekDB 后端的切换边界清晰。
- 数据库迁移包含知识库、文档、分块和后端配置，基础 CRUD 较完整。
- 聊天预处理器与 UI 选择器解耦，未选择知识库时不会增加 RAG 开销。
- 文档 hash 去重、文件大小限制、嵌入批处理、模型维度记录、索引 stale/pending 状态等基础机制已实现。

## 3. 验证结果

### 3.1 自动化与静态检查

| 检查 | 结果 | 说明 |
|---|---|---|
| 全量测试 `python -m pytest -q` | 通过 | `602 passed in 12.86s` |
| 知识库定向测试 | 通过 | 17 项：SQLite、fake SeekDB、重建状态、创建对话框、后端面板、服务容器 |
| Ruff `ruff check misaka/` | 通过 | 无 lint 错误 |
| Mypy（知识库相关 30 个源文件，禁用增量缓存） | 通过 | 无类型错误 |
| `pip check` | 通过 | 当前开发环境无破损依赖 |
| 核心知识库测试覆盖率 | 61% | 1,055 statements / 410 missed；关键失败路径覆盖不足 |

覆盖率较低的核心文件包括：`kb_service.py` 40%、`document_service.py` 52%、解析器 31%、分块器 22%、embedding 0%、reranker 0%。现有集成测试中的解析、嵌入和 SeekDB 多数使用 fake，因此“602 项通过”只证明已有断言满足，不能覆盖生产端点、冻结打包和本报告中的故障路径。

### 3.2 正常路径验证

| 功能 | 结果 | 备注 |
|---|---|---|
| 创建/读取/更新/删除知识库 | 基本通过 | 数据库与 UI 路径已接通；异常清理问题见后文 |
| 文档上传、去重、分块、持久化 | 开发环境通过 | fake embedding + SQLite/SeekDB 路径可完成 |
| TXT/Markdown/DOCX/XLSX/PDF 解析 | 部分通过 | 文本可读取；页/工作表 metadata 错误；`.xls` 不可用 |
| SQLite sqlite-vec 写入与查询 | 开发环境通过 | 真实 sqlite-vec 扩展在当前 Python 环境可加载 |
| SeekDB 适配器 API 兼容性 | 合约通过 | 与本机 pyseekdb 1.4.0 签名匹配；未连接真实服务器 |
| 聊天 RAG 注入 | 基础路径通过 | fake embedding/检索可注入上下文；配置、融合和错误反馈有缺陷 |
| 后端切换与重建提示 | 部分通过 | 后端类型变化可标 stale；同类型远程目标变化不能识别 |

### 3.3 故障注入与边界复现

以下是本次独立构造、可稳定复现且现有测试未覆盖的关键结果：

1. 重处理时模拟新摄取失败：数据库真实分块变为 0，但文档和知识库仍显示 `chunk_count=1`，且知识库仍出现在聊天可选列表。
2. 全量重建时构造 `storage_path` 为空：返回 `success_count=1, error_count=0`，旧分块已删除，知识库却被标为 `active` 和已重建。
3. 嵌入进行中删除文档：删除按钮可用；最终文档行和文件被删除，但 fake 向量后端保留已写入向量，上传任务因外键错误返回 `error`。
4. 模拟远程向量删除失败：删除 API 仍返回成功，本地文档和文件消失，远程向量仍存在。
5. `seekdb_remote` 从一组 host/database 改到另一组：`changed=false`、索引不 stale、原知识库仍可选择，但新目标没有原索引。
6. 同一分块同时命中向量与 BM25：RRF 输出两个内容完全相同、ID 不同的结果。
7. 配置 `top_k=1`、`similarity_threshold=0.9`，检索仍保留 3 条（分数 0.95/0.5/0.1），说明两个用户可见配置未传入/未应用。
8. 多工作表 XLSX 的第二张表内容被分块，但所有分块 metadata 都标成第一张表；两页 PDF 的所有分块都标成第一页；旧 `.xls` 被 openpyxl 直接拒绝。

## 4. 详细问题

### KB-001（P0，已修复）：重处理/重建先删除旧索引，失败后造成数据丢失和虚假可用状态

证据：

- `misaka/services/knowledge/document_service.py:246-271` 在新摄取前删除旧向量和 `kb_chunks`；摄取失败时仅写 `status=error`，没有恢复旧索引，也没有把 `content_text/chunk_count` 清零。
- `misaka/services/knowledge/kb_service.py:170-187` 全量重建先 drop 整个知识库向量集合；每个文档处理完成后依据异常计数决定 `active/error`。
- `misaka/services/knowledge/kb_service.py:243-247` 已删除旧分块后，`storage_path` 为空会直接 `return`，调用方仍增加成功数。
- `misaka/services/knowledge/kb_service.py:99-108` 用文档上的反规范化 `chunk_count` 汇总，而不是统计真实 `kb_chunks`。
- `misaka/services/knowledge/kb_service.py:318-339` 聊天可选性依赖上述缓存统计和 KB 状态。

影响：一次临时模型错误、文件丢失或网络异常就能销毁原本可用的索引；随后 UI 仍可能显示有分块并允许聊天选择，实际检索为空。这既是数据丢失，也是可用性状态错误。

建议：采用“新索引版本构建 -> 校验分块/向量数量 -> 数据库事务切换 active version -> 最后删除旧版本”的 copy-on-write 流程。缺失源文件必须计为失败。所有异常路径从真实 chunk 行重算统计，禁止在未成功切换时调用 `mark_index_rebuilt()`。

### KB-002（P0，已修复）：PyInstaller 发布版缺少默认 RAG 所需运行依赖

证据：

- `misaka.spec:165-170` 明确排除 `numpy`。
- `misaka/services/knowledge/rag/langchain/retriever.py:65-77` 默认 SQLite 混合检索在请求时导入 `rank_bm25.BM25Okapi`；`rank_bm25` 顶层依赖 NumPy。
- `misaka/services/knowledge/rag/langchain/vector_store.py:140-147` 运行时动态导入 `sqlite_vec` 并加载原生扩展。
- 现有 `build/Misaka/Analysis-00.toc` 能看到 `rank_bm25` 和 `sqlite_vec` Python 模块，但 `dist/Misaka/_internal` 中没有 NumPy，也没有 `sqlite_vec/vec0.dll`；所有 PyInstaller TOC 中均未找到 `vec0.dll`。

影响：冻结发布版默认 BM25 路径会因 NumPy 被排除而失败；sqlite-vec 原生扩展也很可能无法加载。检索层会捕获部分异常并退化成空结果，因此用户可能只感知到“知识库没有效果”，而不是明确崩溃。SeekDB/pyseekdb 同样依赖 NumPy，排除规则还会影响替代后端。

建议：移除不兼容的 NumPy排除项，显式收集 sqlite-vec 原生库（使用 `collect_dynamic_libs/collect_data_files` 或自定义 hook），并在 CI 中对冻结目录执行：启动、创建临时 KB、加载 sqlite-vec、写入、查询、BM25 融合的 smoke test。旧产物日期早于本次审查，修复后必须重新构建验证，不能只依赖静态分析。

### KB-003（P1，已修复）：处理中的文档可被删除，导致孤儿向量和外键失败

证据：

- `misaka/services/knowledge/document_service.py:82-108` 先创建文档记录，再等待完整摄取；向量由编排器先写入。
- `misaka/ui/knowledge/components/document_list.py:121-140` 查看、重处理、删除按钮不根据 `pending/parsing/embedding` 状态禁用。
- `misaka/services/knowledge/document_service.py:204-227` 删除不持有文档级锁，也没有取消正在运行的摄取任务。

影响：删除与上传并发时，向量可以在删除之后写入，随后 chunk 行因文档外键已不存在而失败，形成无法由普通 UI 定位/清理的孤儿向量。在远程后端中还构成数据留存风险。

建议：每个文档/知识库引入异步互斥与取消令牌；处理期间禁用删除/重处理，或删除操作先取消并等待任务完成。无论文档行是否仍存在，异常清理都必须以 `document_id` 删除已写向量。

### KB-004（P1，已修复）：向量清理异常被吞掉，本地删除仍报告成功

证据：

- `misaka/services/knowledge/document_service.py:211-227` 捕获向量删除异常后继续删除数据库和文件并返回成功。
- `misaka/services/knowledge/kb_service.py:82-95` 删除整个 KB 时采用相同策略。

影响：网络中断或 SeekDB 故障时，本地元数据被永久删除，远程向量仍保存；之后无法从正常业务记录中得知清理范围，也可能在复用表/过滤错误时产生陈旧检索和隐私风险。

建议：删除应有可恢复状态（`deleting/delete_failed`）和持久化清理队列。只有远程清理确认完成后才最终删除元数据；若业务要求本地先删除，也至少保留 tombstone、backend fingerprint、表名和待清理 document IDs，并向用户明确报告部分失败。

### KB-005（P1，已修复，第二阶段）：SeekDB 远程目标变化不会把索引标记为 stale

证据：

- `misaka/main.py:239-264` 仅比较 `previous != vector_backend`。当后端类型始终是 `seekdb_remote`，修改 host、port、database 或连接身份不会触发 `mark_all_kb_indexes_stale()`。

影响：编排器开始连接新数据库，但 UI 仍把基于旧数据库构建的 KB 视为可用；查询新目标时得到空结果或错误。若不同环境存在同名表，还可能检索到不属于该 KB 的数据。

建议：存储并比较后端身份 fingerprint（backend type + host + port + database/tenant；密码变化通常不需要重建）。目标身份变化时全部标 stale，并阻止选择直到重建成功。

### KB-006（P1，已修复，第二阶段）：RRF 使用不一致的分块 ID，重复返回同一内容

证据：

- `misaka/services/knowledge/rag/langchain/retriever.py:85-94` BM25 结果 ID 被构造成 `chunk_<index>`。
- 向量写入使用 `metadata["chunk_db_id"]` 的 UUID（`misaka/services/knowledge/rag_orchestrator.py:118-137`）。
- `misaka/services/knowledge/rag/langchain/retriever.py:98-121` RRF 按 `chunk_id` 合并，因此同一分块被当成两个结果。

影响：真正同时满足语义和关键词的分块无法获得融合加权，反而占用两个 top-k 名额，重复上下文浪费 token，并可能挤掉其他相关内容。

建议：BM25 结果优先使用 `chunk.metadata["chunk_db_id"]`，缺失时才使用稳定、带文档 ID 的 fallback。融合后增加按真实 chunk ID 的唯一性断言和回归测试。

### KB-007（P1，已修复，第二阶段）：用户配置的 `top_k` 和 `similarity_threshold` 不生效

证据：

- 两项配置可在 `misaka/ui/knowledge/components/kb_create_dialog.py:88-94` 编辑并保存。
- `misaka/services/chat/preprocessors.py:99-108` 调用 `retrieve()` 时没有传入每个 KB 的 `top_k` 或 threshold。
- `misaka/services/knowledge/rag_orchestrator.py:163-219` 只接受单个全局 `top_k=5`，没有相似度阈值参数。
- `reranker_top_k` 会生效，但在多 KB 场景中只取某一个 KB 的配置，见 KB-017。

影响：界面提供了看似有效的检索精度控制，但实际结果数和低分过滤不受其影响。用户可能错误地认为已经提高了检索阈值或限制了上下文大小。

建议：明确多 KB 合并语义。推荐每个 KB 使用自身的 candidate top-k/threshold 先过滤，再以会话级 final top-k 合并；阈值需根据后端统一后的相似度定义应用。UI 保存后增加配置传播测试。

### KB-008（P1，已修复，第二阶段）：修改分块参数不会重建已有索引

证据：

- `misaka/ui/knowledge/components/kb_create_dialog.py:168-181` 只有 embedding router/model 变化才进入确认和重建流程。
- `chunk_size`、`chunk_overlap` 改动直接保存，但现有 `kb_chunks` 和向量保持旧切分。

影响：配置页面显示的是新参数，实际检索索引仍使用旧参数，且没有 stale 标记，后续排障无法信任 KB 配置。

建议：将 chunk size/overlap、解析策略和 embedding 模型/维度都纳入 `index_fingerprint`。任何影响索引内容的字段变化都标 stale 并要求重建；也可先保存为 pending config，成功切换后再替换 active config。

### KB-009（P1，已修复，第二阶段）：没有 10 秒总检索超时，且单 KB 失败会静默降级

证据：

- 需求文档要求检索超过 10 秒取消 RAG 并通知用户。
- `misaka/services/knowledge/rag_orchestrator.py:163-219` 没有包围整个检索的 timeout；embedding 客户端自身 60 秒、reranker 30 秒，SeekDB 同步调用没有统一查询超时。
- 同文件 `:190-216` 捕获各 KB 的 embedding、retrieval、reranker 异常并继续，最终可能返回空列表。
- `misaka/services/chat/preprocessors.py:103-115` 空结果被视为正常，失败通知仅覆盖抛到外层的异常。

影响：聊天发送可能长时间卡住；服务故障时用户收到普通模型回答，却不知道知识库根本没有参与，产生高风险的错误信任。

建议：用 `asyncio.timeout(10)` 或可配置截止时间包围整个 RAG；返回结构化的 `results + per_kb_errors + timed_out`，在保留部分结果时提示部分失败，全部失败时必须通知并在消息上标注 RAG 未生效。

### KB-010（P2，已复现）：PDF 页码、Excel 工作表 metadata 丢失，且声明支持的 `.xls` 实际不可读

证据：

- `misaka/services/knowledge/rag/langchain/parser.py:34-45` 把 loader 返回的所有 Document 文本拼成一个字符串，只保留第一项 metadata。
- `_OpenpyxlLoader` 本来会在 `:106-145` 为每个 worksheet 创建 Document，但随后被上述逻辑压平。
- `misaka/services/knowledge/document_service.py:27-36` 声明 `.xls` 和 `.xlsx` 都支持，而 parser 对两者都使用 openpyxl；openpyxl 明确拒绝旧 `.xls`。

影响：引用页码/工作表错误，文档查看和未来引用展示不可信；用户可以选择 `.xls`，但上传必然失败。

建议：让 parser 返回带各自 metadata 的逻辑文档列表，分块器逐 Document 分块并继承 `page/sheet_name`；去掉 `.xls` 声明，或引入 xlrd 等真正支持旧格式的 loader 和测试样本。

### KB-011（P2，已复现）：模型可用性检查忽略 `is_selected`

证据：

- `misaka/services/knowledge/kb_service.py:112-140` 只判断 router 配置中是否存在同 model ID，不检查模型是否被用户选中。
- 实际上传/重处理的模型选择来自 `misaka/services/settings/router_config_service.py:274-278` 的 selected-only 列表。

影响：UI 可显示 embedding 模型可用，但上传对话框找不到该模型并提前返回，用户没有得到一致的不可用提示。

建议：统一“可用”的定义和查询入口，同时校验 router 启用状态、模型 `is_selected`、base URL/API key 基本完整性；上传按钮应显示明确错误而不是静默返回。

### KB-012（P2，源码确认）：多个重操作仍在 UI 事件循环同步执行

证据：

- `misaka/services/knowledge/document_service.py:59-86` 在 async 上传方法中同步执行 stat、SHA-256 全文件读取和最多 100 MB 文件复制。
- `misaka/services/knowledge/rag_orchestrator.py:106-113` 同步分块；SQLite BM25 会读取该 KB 全部分块并同步构建/计算语料。
- `misaka/services/knowledge/rag/langchain/retriever.py:51-59` 同步执行向量查询与 BM25。
- SeekDB upsert/search/delete/refresh 是同步 SDK 调用，但从 async UI/RAG 路径直接调用。

影响：大文件、大知识库或远程网络抖动时会卡住 Flet UI，与 `docs/architecture/PERFORMANCE.md` 的“Never block main thread”规则冲突。BM25 每次查询都全量加载和重建，复杂度随分块数量快速上升。

建议：文件 I/O、解析、分块、SQLite/SeekDB 同步调用放入 `asyncio.to_thread` 或专用 worker；使用持久化/增量 BM25 索引，限制并发与队列长度，并对 10k/100k 分块建立性能基准。

### KB-013（P2，已由并发复现佐证）：数据库、文件和向量后端之间没有原子提交协议

证据：

- 编排器先写向量，`DocumentService` 后写 `kb_chunks` 和文档状态；后半段失败会留下孤儿向量。
- 删除方向则先尝试向量清理，再无条件删除本地记录，远程失败无法回滚。
- `LCSqliteVecStore.add_chunks()` 使用 `zip(..., strict=False)`，没有验证 chunks/embeddings 数量一致。

影响：任一步骤崩溃、进程退出或数据库提交失败都会使三类存储分叉，且当前没有启动时 reconciliation。

建议：引入 ingest job/index version、幂等操作键和补偿事务；本地 SQLite DB 与 sqlite-vec 可共享连接/事务时尽量原子提交；远程后端采用 outbox/saga。启动时扫描 processing/deleting 超时任务并校验实际计数。

### KB-014（P2，源码确认）：高级数值配置缺少领域校验

证据：

- `misaka/ui/knowledge/components/kb_create_dialog.py:240-251` 的 `_safe_int/_safe_float` 只做解析与默认值回退。
- 没有约束 `chunk_size > 0`、`0 <= overlap < chunk_size`、`top_k/reranker_top_k > 0`、threshold 的有效范围，以及拒绝 NaN/Infinity。

影响：无效配置可写入数据库，并在 splitter、切片、排序或网络请求处以难以理解的方式失败。

建议：在 service 层建立唯一的配置校验器，UI 仅负责显示字段错误；数据库写入和导入路径同样调用。为边界值、NaN/Infinity 和 overlap 关系增加参数化测试。

### KB-015（P2，安全风险）：知识库内容直接进入提示词，缺少注入边界处理

证据：

- `misaka/services/knowledge/rag_orchestrator.py:221-239` 把用户可上传的文档原文直接拼入 XML 风格标签，没有转义标签字符，也没有明确告知模型“文档中的指令是不可信数据”。

影响：恶意或无意的文档文本可以闭合标签、伪造结构、指示模型忽略用户意图或泄露上下文。这不是本地代码执行漏洞，但会破坏回答可信性，尤其当 KB 包含外部来源文档时。

建议：使用结构化消息/严格序列化并转义分隔符；系统提示明确声明上下文只提供事实、不得遵循其中指令；保留来源与信任级别，必要时做内容安全扫描。增加包含闭合标签和 prompt injection 文本的评估用例。

### KB-016（P2，源码确认）：重排器对畸形响应校验不完整

证据：

- `misaka/services/knowledge/rag/langchain/reranker.py:60-74` 只拒绝 `index >= len(results)`；负数 index 会按 Python 语义选取尾部结果。
- 重复 index 不去重；空/缺失结果可被当作成功的空重排，不一定回退到原结果。

影响：不标准的 OpenAI-compatible reranker 响应会重复、错配或清空检索结果。

建议：要求 index 为非负整数、范围内且唯一，score 为有限数；响应无有效项时记录结构化错误并回退原排序。

### KB-017（P2，源码确认）：多知识库的 reranker 选择依赖无序集合

证据：

- `misaka/ui/knowledge/components/kb_selector.py:207-213` 使用 `list(set(...))` 保存选择，顺序不稳定。
- `misaka/services/chat/preprocessors.py:129-156` 遍历 KB，并采用遇到的第一个 reranker 配置作为所有结果的全局重排器。

影响：选择多个配置不同 reranker 的 KB 时，实际使用哪个模型/阈值可能随顺序变化，结果不可重复；一个 KB 的配置会无提示地覆盖其他 KB。

建议：保持用户选择顺序并显式定义策略：要么每 KB 独立重排后融合，要么由会话提供统一 reranker。存在冲突时 UI 应提示，而不是隐式取第一个。

### KB-018（P3，源码确认）：列表和文档查看器在大规模下会制造过多 UI 控件/内存复制

证据：

- `misaka/ui/knowledge/components/document_list.py:62` 一次性为全部文档创建行，不是真正虚拟化。
- 文档查看器“加载更多”会反复生成更大的内容前缀，复制按钮可把最多 100 MB 原文一次性放入剪贴板。

影响：文档多或单文档大时，页面构建、更新和内存占用明显上升。

建议：分页/虚拟列表；查看器按页或按块读取而不是保存整份文本控件；复制操作设置合理上限并提供导出文件。

### KB-019（P3，源码确认）：文件系统异常与数据库状态处理不对称

证据：

- 创建 KB 时数据库 commit 早于存储目录创建，mkdir 失败会留下不可用 KB 记录。
- 删除 KB 使用 `shutil.rmtree(..., ignore_errors=True)`，目录删除失败仍返回成功。

影响：磁盘权限、文件占用或空间错误后出现幽灵记录/残留文件，用户无法从 UI 得知。

建议：创建采用补偿删除或先准备临时目录再提交；删除记录并展示文件清理失败，保留重试任务。

### KB-020（P3，设计风险）：表名截断和旧后端资源缺少生命周期管理

证据：

- 每 KB 的向量表名只使用 UUID 前 8 个十六进制字符，约 32 bit 命名空间；规模增大后碰撞概率不可忽略。
- 后端切换只标 stale，不清理旧后端集合；删除 KB 后 pending rebuild IDs 也没有统一清除。

影响：长期运行可能积累远程/本地残留资源；极大规模下表名碰撞可能让两个 KB 共享/覆盖表。

建议：使用完整 UUID 或至少 128-bit 编码；为后端资源记录 backend fingerprint、collection ID 和生命周期状态，提供迁移/清理命令及 orphan audit。

## 5. 与设计文档的主要偏差

| 设计要求 | 当前实现 | 结论 |
|---|---|---|
| RAG 超过 10 秒取消并通知 | `retrieve_with_diagnostics()` 以 10 秒全局 deadline 返回 `timed_out`，聊天页显示通知 | 已实现 |
| 文档后台处理不阻塞 UI | 解析使用 `to_thread`，但 hash/copy/chunk/BM25/SeekDB 等仍同步 | 部分实现 |
| 嵌入批次并发度 3 | 批次顺序执行 | 未实现 |
| 上传显示 parse/chunk/embed 进度 | 对话框只显示每个文件的粗状态，未传 `on_progress` | 部分实现 |
| 上传路径安全检查 | 存在相关设计，但上传链路未调用统一 `is_path_safe` | 未实现 |
| 删除处理中文档前等待或中止任务 | 操作不按状态禁用，也无任务取消/锁 | 未实现 |
| KB 在处理期使用 building/error 状态机 | 普通上传/重处理通常不改变 KB 状态 | 部分实现 |
| PDF 按页、Excel 按表保留 metadata | 全部文本压平并只保留首项 metadata | 未实现 |
| 聊天选择依据真实可用嵌入分块 | 依赖反规范化的 KB `chunk_count` | 不可靠 |
| KB 的 top-k/threshold 配置生效 | 预处理器传递每 KB 策略；归一化后阈值过滤，再应用会话级 final top-k | 已实现 |

## 6. 修复优先级与实施建议

### 第一阶段：阻止数据丢失和发布版失效

1. 重构 ingest/rebuild 为版本化、copy-on-write 索引切换；任何失败保留旧 active 索引。
2. 为上传、重处理、重建、删除增加 job 状态、文档/KB 互斥和取消等待。
3. 向量删除失败进入持久化清理队列，禁止无痕吞错。
4. 修复 PyInstaller：NumPy、rank-bm25、sqlite-vec 原生 DLL，并新增冻结版 RAG smoke test。
5. 从真实 `kb_chunks`/向量统计做 reconciliation，修复已有虚假计数和孤儿数据。

### 第二阶段：恢复检索语义正确性

1. 统一 BM25 与向量结果的 `chunk_db_id`，增加融合去重测试。
2. 传播并应用每 KB 的 top-k/threshold；定义多 KB final top-k 和 reranker 策略。
3. 后端 fingerprint 覆盖远程 host/port/database，目标变化即 stale。
4. 加入 10 秒总 deadline、部分失败结构化结果和用户可见通知。
5. chunk/embedding/parser 配置纳入 index fingerprint，变更必须重建。

### 第三阶段：兼容性、性能与可信性

1. 保留 PDF page、Excel sheet metadata；删除虚假的 `.xls` 支持或加入真正 loader。
2. 把文件 I/O、chunk、BM25、SeekDB 同步调用移出 UI 事件循环；构建增量 BM25。
3. service 层统一数值验证、模型可用性定义和 reranker 响应验证。
4. 对知识库文本做结构化转义和 prompt-injection 防护提示。
5. 引入大规模基准、分页/虚拟化和后端 orphan audit 工具。

## 7. 建议补充的测试

- 重处理失败后旧索引仍可查询，统计不变。
- 缺失 storage file 的全量重建必须失败且不能 `mark_index_rebuilt`。
- 上传与删除/重处理并发，确保取消、无 FK 错误、无孤儿向量。
- 远程删除失败的 tombstone/outbox 重试和最终一致性。
- remote host/database 变化触发 stale；仅密码轮换不触发重建。
- 同一分块同时命中 vector/BM25，只输出一次且融合分数增加。
- top-k、threshold、chunk 配置从 UI -> DB -> preprocessor -> retriever 的传播测试。
- PDF 多页、XLSX 多 sheet metadata；`.xls` 的明确支持或拒绝测试。
- 负 index、重复 index、NaN score、空 reranker 响应。
- 10 秒 timeout、单 KB 部分失败、全部失败及用户通知。
- 10k/100k chunks 的上传、BM25、切换页面和聊天延迟基准。
- PyInstaller 构建后 sqlite-vec load/write/search + BM25 的 smoke test。

## 8. 第一阶段实施记录（2026-08-11）

### 8.1 已完成范围

本次仅落实第 6 节“第一阶段”的五项内容，对应 KB-001、KB-002、KB-003、KB-004 及统计 reconciliation。第二、三阶段问题仍保持原审查结论，未在本次修复中标记完成。

### 8.2 实施方案与变更

1. 新增数据库 migration v7。`knowledge_bases.active_index_version` 指向聊天正在使用的版本；`kb_chunks.index_version` 将分块与索引版本绑定；历史未版本化数据继续使用空版本对应的旧表名，保证升级兼容。
2. 新增 copy-on-write 索引流程。上传、重处理、全量重建和删除都先构建完整的新版本向量表/collection；全部文件解析、分块、嵌入和向量写入成功后，才在一个 SQLite 事务中写入分块、更新文档元数据/真实统计并切换 active version。失败或取消会删除 staging 版本，旧 active version、旧统计和聊天可用性保持不变。
3. 新增 `kb_jobs` 持久化作业状态及 KB 级异步互斥协调器。上传、重处理、重建、文档删除和 KB 删除均串行化；删除操作先取消并等待同一 KB 的活动任务。处理中的文档在 UI 中禁用重处理和删除按钮。
4. 新增 `kb_cleanup_jobs` 持久化清理队列。远端/本地向量版本删除失败不再被吞掉：会记录待重试任务，应用启动时重试；成功后再删除退役版本的 `kb_chunks` 行。SeekDB adapter 不再吞掉 `delete_collection` 异常。
5. 统计和聊天选择改为读取 active index version 的真实 `kb_chunks`。这会修复历史反规范化 `document_count/chunk_count` 与实际分块不一致时的虚假可选状态。
6. PyInstaller spec 显式保留 NumPy、`rank_bm25`、`sqlite_vec`，并通过 `collect_dynamic_libs` / `collect_data_files` 收集 sqlite-vec 原生库。新增 `--rag-smoke`：在冻结产物中验证 sqlite-vec 加载、写入、检索和 NumPy 支持的 BM25 融合；CI Windows job 和 Windows release job 均会执行该 smoke test。

### 8.3 新增回归验证

- 重处理解析失败后，active version、真实分块统计和聊天可选性保持不变。
- 源文件缺失的全量重建返回失败，且不会执行 `mark_index_rebuilt()`。
- 退役向量索引删除失败会进入持久化队列；恢复后可重试并清理历史分块。
- 删除会取消并等待活动上传，确保不会留下孤儿向量或外键失败。
- 已执行针对性回归、静态检查和源代码 RAG smoke；冻结产物 smoke 由新增 CI job 验证。
- 可选的真实 SeekDB 远程集成测试与真实 OpenAI-compatible embedding/reranker contract test（凭据由 CI secret 提供）。

## 9. 第二阶段实施记录（2026-08-11）

### 9.1 已完成范围

本次落实第 6 节“第二阶段”的五项内容，对应 KB-005、KB-006、KB-007、KB-008 和 KB-009。第一阶段的修复保持有效；第三阶段项目仍维持原审查结论，未在本次变更中标记完成。

### 9.2 实施方案与变更

1. 为远程 SeekDB 保存无凭据的后端目标 fingerprint：包含 backend、host、port、user 和 database，明确排除 password。目标变化会把有源文档的 KB 加入持久化 stale 队列，密码轮换仅重建连接而不要求重嵌入。
2. LangChain BM25 检索改为优先使用 `chunk_db_id`；缺失时采用包含 document ID、chunk index 与内容摘要的稳定 fallback。RRF 在各路结果内部和融合时均按真实 ID 去重，因此同一命中只保留一次并获得两路权重。
3. 新增 `KBRetrievalConfig`。`RAGPreprocessor` 从已保存的 KB 配置构造每 KB candidate top-k、归一化阈值和 reranker 配置；编排器先分别检索、可选地按该 KB 独立重排、归一化并过滤，再按会话级 final top-k 合并。该策略不再依赖 KB 选择顺序，也不会用一个 KB 的重排器覆盖另一个 KB。
4. 新增 `RAGRetrievalOutcome` 和 `retrieve_with_diagnostics()`：整个检索管道有 10 秒全局 deadline，返回 `results`、`per_kb_errors` 与 `timed_out`。单 KB/重排失败保留其他 KB 结果；聊天页面对超时、全部失败和部分失败分别显示可见提示。向量与 SeekDB 检索被移至工作线程，避免同步查询阻塞 deadline 的事件循环。
5. 新增 migration v8 和 `knowledge_bases.active_index_fingerprint`。该 fingerprint 覆盖 embedding model/router/dimensions、chunk size/overlap 以及 parser/chunker 策略版本；成功激活新索引时原子保存。编辑分块或嵌入配置会显示重建确认、进入 stale 队列并阻止聊天选择，重建成功后才清除 stale。

### 9.3 新增回归验证

- 同一分块同时命中向量与 BM25 时仅输出一次，融合分数包含两路权重；没有 `chunk_db_id` 的不同文档不会发生 fallback ID 碰撞。
- 每 KB 的 candidate top-k、阈值、会话级 final top-k 与 reranker 配置均经过 preprocessor 到 orchestrator 的传播验证。
- SeekDB host 改变会 stale；仅 password 改变不会 stale，且 password 不会写入 fingerprint。
- 分块设置改动会 stale 并从聊天选择中移除；数据库升级会添加 active index fingerprint 列。
- 10 秒 deadline、单 KB 部分失败和 fake SeekDB/SQLite 聊天主路径均有自动化回归覆盖。

## 10. 最新修复后判定

| 判定项 | 结论 |
|---|---|
| 架构完整度 | 良好，抽象和模块边界清楚 |
| 开发环境基础流程 | 可运行 |
| 失败恢复与数据一致性 | 第一阶段已修复 copy-on-write、作业协调和清理队列；第三阶段仍需继续处理文件系统与规模化项 |
| 检索逻辑正确性 | 第二阶段已修复 RRF ID、一致去重、每 KB top-k/threshold、确定性多 KB reranker 策略 |
| 文件格式语义 | 部分正确，内容可读但 page/sheet metadata 错，`.xls` 虚假支持 |
| UI 响应与规模化 | 小规模可用，大文件/大 KB 有阻塞风险 |
| 错误可观察性 | 第二阶段已提供 deadline/部分失败结构化结果与聊天可见通知；其余后台任务可观测性持续改进 |
| 安全与隐私边界 | 需加强，存在孤儿远程向量和 prompt injection 风险 |
| 冻结发布版 | 当前不可判定为可用，已有证据显示关键依赖缺失 |
| 生产发布建议 | 暂缓；先完成 P0/P1 修复与真实/冻结 E2E |

因此，完成第一、二阶段后，知识库的失败恢复和检索语义关键路径已具备回归保护；仍须完成第三阶段的格式语义、性能、输入验证和可信性工作，才可达到完整的生产发布标准。
