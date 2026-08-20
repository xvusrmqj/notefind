# 第三步：Web UI

目标：提供浏览器界面，替代 CLI 交互，支持搜索、问答、同步状态查看。

## 技术选型（建议）

- 后端：FastAPI（Python，与第一、二步代码同语言，直接复用 sync / 检索逻辑）
- 前端：单页应用（React）

## 功能清单

### 1. 问答页（核心）
- 输入框：自然语言提问
- 回答区：流式输出 LLM 回答（SSE）
- 引用区：每个引用显示 `file_path + heading`，点击可跳转查看原文

### 2. 搜索页（纯检索，不问 LLM）
- 输入关键词 / 自然语言
- 结果列表：chunk 内容摘要 + 相似度/RRF 分数 + 来源
- 可切换检索模式：向量 / 全文 / 混合

### 3. 同步管理页
- 触发同步按钮（后台任务执行，显示进度）
- 同步统计：文档总数、chunk 总数、上次同步时间、新增/更新/删除数量

### 4. 文档浏览（可选）
- 文档列表（按目录 / 修改时间）
- 点击查看文档的所有 chunks

## API 设计（草案）

```
POST /a​pi/sync                # 触发同步（后台任务，重复触发返回 409）
GET  /a​pi/sync/status         # 同步状态与统计
POST /a​pi/search              # 纯检索 { query, mode: vec|fts|hybrid, k }
POST /a​pi/ask                 # RAG 问答（SSE 流式返回）
GET  /a​pi/documents           # 文档列表
GET  /a​pi/documents/{id}      # 文档详情 + chunks
```

### `GET /a​pi/sync/status` 响应字段

```json
{
  "running": false,
  "current": 12,          // 同步进行中：当前第几个文件
  "total": 42,            // 同步进行中：本次扫描到的文件总数
  "last_run": "2026-08-20T10:00:00+08:00",
  "last_result": { "added": 3, "updated": 1, "deleted": 0 },
  "stats": { "documents": 42, "chunks": 517 }
}
```

> sync 已有进度回调（`cli.py` 的 `_progress`），后端复用同一回调更新内存中的状态即可。

### `POST /a​pi/ask` SSE 事件格式

约定事件类型，前端按 `event` 分发渲染：

```
event: citations\ndata: [{"chunk_id": 1, "file_path": "...", "heading": "...", "score": 0.83}, ...]\n\n
event: delta\ndata: {"text": "回答的增量片段"}\n\n
event: done\ndata: {}\n\n
event: error\ndata: {"message": "..."}\n\n
```

- `citations` 先于所有 `delta` 下发，前端可先渲染引用区占位
- 出错时发 `error` 事件并结束流

## 注意事项

- LLM / embedding 服务都在本地，注意并发限制（如同步进行中时排队问答请求）
- 同步任务用后台队列（如 asyncio task / 简单锁），避免重复触发
- 引用跳转本地文件可用 `obsidian://open?path=...` 之类的 URI scheme
- **同步阻塞事件循环**：`sync.py` / `retriever.py` / `qa.py` 均为同步代码（psycopg、requests），在 FastA​PI 中必须用 `asyncio.to_thread()` 包装，或路由直接用 `def`（非 `async def`，FastA​PI 自动放入线程池），否则 SSE 流式输出会被阻塞
- **安全**：服务只绑定 `127.0.0.1`（uvicorn `--host 127.0.0.1`），避免暴露到局域网；无需鉴权
- **前端构建**：React + Vite，构建产物由 FastA​PI 静态托管（`StaticFiles`），部署时单进程即可

## 实现说明（2026-08-20 完成）

代码结构（第三步同时做了分包重构）：

```
src/notefind/
├── core/      # 领域逻辑：config/db/scanner/parsers/chunker/embedding/sync/retriever/qa
├── cli/       # CLI 接口：main.py（sync / ask / serve）
└── webapi/    # Web 后端：app.py（路由+SSE+静态托管）、schemas.py、sync_manager.py
web/           # React + Vite 前端（npm 工程，构建产物 web/dist 由 FastA​PI 托管）
```

与草案的差异 / 要点：

- `SearchHit` 增加 `chunk_id`（三条检索 SQL 均返回 `c.id`），citations 事件携带 chunk 原文，前端引用点击页内展开（不用 obsidian:// URI）
- `qa.py` 新增 `ask_stream()`：检索完成后 `chain.stream()` 逐 token 产出；`/api/ask` 用 `asyncio.to_thread` 包装阻塞调用，SSE 事件序列 citations → delta* → done / error
- ask 请求用 `asyncio.Semaphore(1)` 串行化（本地 LLM 单并发，排队执行）
- 同步：`SyncManager` 后台 asyncio task + `to_thread(sync_all)`，重复触发 409；progress 回调更新内存状态；stats 实时查 DB 计数
- 文档浏览：`GET /api/documents` 支持分页 + 路径过滤（ILIKE），详情返回全部 chunks
- 启动：`uv run notefind serve`（默认 127.0.0.1:8000）；开发模式 `cd web && npm run dev`（Vite 代理 /api）
