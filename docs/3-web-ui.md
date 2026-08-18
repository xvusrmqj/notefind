# 第三步：Web UI

目标：提供浏览器界面，替代 CLI 交互，支持搜索、问答、同步状态查看。

## 技术选型（建议）

- 后端：FastAPI（Python，与第一、二步代码同语言，直接复用 sync / 检索逻辑）
- 前端：单页应用（React / Vue 均可），或先用 FastAPI + Jinja2 简单页面起步

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
POST /api/sync                # 触发同步（后台任务）
GET  /api/sync/status         # 同步状态与统计
POST /api/search              # 纯检索 { query, mode: vec|fts|hybrid, k }
POST /api/ask                 # RAG 问答（SSE 流式返回）
GET  /api/documents           # 文档列表
GET  /api/documents/{id}      # 文档详情 + chunks
```

## 注意事项

- LLM / embedding 服务都在本地，注意并发限制（如同步进行中时排队问答请求）
- 同步任务用后台队列（如 asyncio task / 简单锁），避免重复触发
- 引用跳转本地文件可用 `obsidian://open?path=...` 之类的 URI scheme
