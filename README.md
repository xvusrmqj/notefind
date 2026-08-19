# notefind

使用 RAG 技术将本地笔记本（zim / obsidian / logseq / markdown）向量化存入 PostgreSQL (pgvector)，
支持自然语言搜索与 LLM 问答，全程本地运行。

## 使用说明

### 1. 前置条件

- Python >= 3.11
- PostgreSQL（安装 `pgvector` 扩展）
- 本地 LLM 服务（OpenAI 兼容接口，默认 `http://localhost:8317/v1`）
- 本地 Embedding 服务（OpenAI 兼容接口，默认 `http://localhost:11434/v1`，如 Ollama）

### 2. 安装

```sh
uv sync
```

> 后续所有命令（CLI 和 scripts/ 下的脚本）都通过 uv 运行：`uv run notefind ...`、`uv run python scripts/xxx.py`，无需激活 venv

### 3. 配置

在项目根目录创建 `.env` 文件（或直接使用环境变量）：

```dotenv
# 数据库连接（需已安装 pgvector 扩展）
DATABASE_URL=postgresql://notefind:123456@localhost:5432/notefind

# Chat LLM（OpenAI 兼容）
LLM_BASE_URL=http://localhost:8317/v1
LLM_MODEL=glm-5.1
LLM_API_KEY=your-api-key-1

# Embedding 模型（OpenAI 兼容）
EMBED_BASE_URL=http://localhost:11434/v1
EMBED_MODEL=qwen3-embedding:0.6b
EMBED_API_KEY=ollama

# 笔记目录，格式: source_type:/abs/path，多个用逗号分隔
# source_type 支持: zim / obsidian / logseq / markdown
NOTE_DIRS=zim:/home/olv/Notes/zim,obsidian:/home/olv/Notes/vault

# 可选
TOP_K=10
EMBED_BATCH_SIZE=32
# 全文检索分词配置（pg_jieba 的配置名为 jiebacfg，须与 migrate_002.py 一致）
TSV_CONFIG=jiebacfg
```

### 4. 初始化数据库

```sh
uv run python scripts/migrate_001.py   # 建表 + pgvector 索引
uv run python scripts/migrate_002.py   # content_tsv 生成列 + GIN 索引（需先安装 pg_jieba）
uv run python scripts/check_schema.py  # 校验 schema
```

> pg_jieba 安装：apt 无预编译包时需源码编译（cmake + postgresql-server-dev-18），详见 docs/2-hybrid-search.md。

### 5. 同步笔记

扫描笔记目录并增量入库（mtime 预过滤 + SHA-256 判断变化，只更新有变动的文件）：

```sh
uv run notefind sync
```

### 6. 提问

自然语言检索 + LLM 回答，并附引用来源：

```sh
uv run notefind ask "部署流程里数据库备份是怎么做的？"
```

加 `--show-context` 同时显示检索到的原文片段；`--retrieval hybrid|vector|fts` 切换检索模式（默认 hybrid，RRF 融合）：

```sh
uv run notefind ask "部署流程里数据库备份是怎么做的？" --retrieval fts
```

### 7. 自检（可选）

```sh
uv run python scripts/selftest.py        # 端到端自检
uv run python scripts/selftest_embed.py  # embedding 服务连通性自检
```

## Roadmap

- [x] 第一步：基础版 —— 扫描入库 + 向量检索 + CLI 问答（docs/1-basic.md）
- [x] 第二步：混合检索 —— 向量 + 全文 RRF 融合（docs/2-hybrid-search.md）
- [ ] 第三步：Web UI —— 搜索 / 问答 / 同步管理（docs/3-web-ui.md）
- [ ] 第四步：附件向量化 —— 用 LangChain loader 提取 PDF / Office 附件文本并入库（docs/4-attachments.md）

thinking：
- 笔记更新， 数据库中的向量怎么更新？
  - 每次全量找一遍就行（mtime 预过滤 + SHA-256 判断变化，详见 docs/1-basic.md）。
- 检索：向量 + 全文混合检索（RRF 融合），Qwen3 查询侧加 "query:" 前缀。
- 文件删除：同步删除 documents 行，cascade 清理 chunks。
