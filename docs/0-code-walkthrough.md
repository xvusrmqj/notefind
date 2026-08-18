# notefind 第一版：代码结构说明

本文档解释第一版实现生成的所有文件，以及它们如何协作完成
`扫描笔记 → 入库 → 向量检索 → LLM 回答` 这个闭环。

## 目录总览

```
notefind/
├── pyproject.toml          # 项目定义 + 依赖 + CLI 入口
├── .env                    # 本地配置（含密码，不要提交）
├── .env.example            # 配置模板
├── docs/                   # 设计文档（需求来源）
├── scripts/                # 一次性运维/自测脚本
└── src/notefind/           # 主代码
    ├── __init__.py
    ├── config.py           # 配置加载
    ├── db.py               # 数据库连接池
    ├── scanner.py          # 文件扫描 + 哈希
    ├── parsers.py          # zim/markdown 解析
    ├── chunker.py          # 切分策略
    ├── embedding.py        # Embedding 客户端
    ├── sync.py             # 入库业务逻辑（核心）
    ├── retriever.py        # 向量检索
    ├── qa.py               # RAG 问答
    └── cli.py              # 命令行入口
```

## 数据流

```
sync 命令:
  config → scanner(扫描+mtime过滤) → sha256 → parsers(转Markdown)
    → chunker(切分+heading路径) → embedding(批量向量化)
    → sync(写 documents/chunks 表)

ask 命令:
  config → embedding("query: "+问题) → retriever(cosine top-k SQL)
    → qa(拼context → LLM) → 答案 + 引用来源
```

---

## 逐文件说明

### `pyproject.toml`
- 用 uv 管理的项目定义：依赖、Python 版本（≥3.11）
- 关键行：`notefind = "notefind.cli:app"` 注册了 `notefind` 命令，
  安装后可直接 `uv run notefind sync`
- 依赖分三类：
  - 数据库：`psycopg[binary,pool]`（PostgreSQL 驱动+连接池）、`pgvector`
  - LangChain：`langchain-openai`（模型客户端）、`langchain-text-splitters`（切分）
  - CLI/配置：`typer`、`pydantic-settings`、`python-dotenv`

### `.env` / `.env.example`
所有可变配置集中在这里，代码不硬编码任何地址：
- `DATABASE_URL`：PostgreSQL 连接串
- `LLM_BASE_URL` / `LLM_MODEL`：本地 chat 模型（localhost:8317, glm-5.1）
- `EMBED_BASE_URL` / `EMBED_MODEL`：本地 embedding（localhost:11434, qwen3-embedding:0.6b）
- `NOTE_DIRS`：笔记目录列表，格式 `source_type:/绝对路径`，逗号分隔。
  **加新目录只需改这里，不用改代码**
- `TOP_K` / `EMBED_BATCH_SIZE`：检索条数 / 每批向量化条数

### `src/notefind/config.py`
- 用 pydantic-settings 把 `.env` 读成强类型的 `Settings` 对象
- `NoteDir.parse()` 解析 `NOTE_DIRS` 的每一条 `source_type:path`
- 所有模块都接收 `Settings`，不自己读环境变量

### `src/notefind/db.py`
- psycopg 连接池（1~4 连接），全进程共享一个实例
- `init_pool()` / `get_pool()` / `close_pool()` 三个函数
- 池创建时对每个连接执行 `register_vector`（pgvector 的类型适配）

### `src/notefind/scanner.py`
- `scan_dir(note_dir)`：递归扫描一个目录，按 source_type 过滤扩展名
  （zim→`.txt`，obsidian→`.md`），跳过 `.git`/`.obsidian`/`.trash` 等目录
- `ScannedFile`：带 `path`、`source_type`、`mtime` 的文件记录
- `sha256_of(path)`：流式计算文件哈希（不整读入内存）

### `src/notefind/parsers.py`
把不同格式统一转成 Markdown，后续只需处理一种格式：
- `parse_markdown()`：识别并剥离 YAML front matter（简单 key:value 解析），
  提取 title
- `parse_zim()`：zim wiki → Markdown
  - 校验文件头 `Content-Type: text/x-zim-wiki`（不是则按纯文本处理）
  - 跳过 `Creation-Date:` 等元信息行
  - `~~~代码块~~~` → ` ```代码块``` `
  - `====== 标题 ======` → `# 标题`（注意 zim 的 `=` 越多级别越高，
    与 Markdown 相反，已做换算：6 个 `=` → `#`）

### `src/notefind/chunker.py`
按 docs/1-basic.md 的切分策略实现：
- 先用 LangChain 的 `MarkdownHeaderTextSplitter` 按标题层级（#~####）切，
  并把标题路径（如 `项目 A / 设计`）存进 metadata → 最终写入 `heading` 列
- 段落超过 400 字符时用 `RecursiveCharacterTextSplitter` 再切（带 50 字符重叠）
- 含代码块的段落用专门的分隔符列表切，尽量不切碎 ` ``` ` 块
- 输出 `Chunk(chunk_index, heading, content)` 列表，index 重新编号保证连续

### `src/notefind/embedding.py`
封装 Qwen3-Embedding 的非对称检索约定：
- `embed_query()`：查询侧加 `"query: "` 前缀（Qwen3 要求）
- `embed_documents_batched()`：文档侧不加前缀，按 `EMBED_BATCH_SIZE` 分批
- 底层是 `langchain_openai.OpenAIEmbeddings`，指向本地 ollama 的
  OpenAI 兼容接口，`dimensions=1024` 对应表的 `VECTOR(1024)`

### `src/notefind/sync.py`（核心）
严格实现 docs/1-basic.md 的入库流程图：
1. 加载数据库中所有 documents（file_path → id/hash/mtime）
2. 扫描磁盘，**磁盘没有而库里有 → 删除 document**（cascade 清 chunks）
3. 逐文件：
   - mtime 未变 → skip（不算 hash，省 IO）
   - hash 相同 → 只刷新 mtime，不重建 chunks
   - 有变化 → 解析 → 切分 → 批量 embedding → **单文档一个事务**写入
     （新增或更新 document 行 + 全量替换 chunks）
4. `SyncStats` 统计扫描/新增/更新/跳过/删除/错误
- `progress` 回调让 CLI 打印 `[3/25] add xxx.md` 进度

### `src/notefind/retriever.py`
就是 docs/1-basic.md 里那段检索 SQL 的封装：
- cosine 距离 `<=>`，`1 - distance` 作为相似度，top-k（默认 10）
- 注意 `%(query_vec)s::vector` 强转：psycopg 传 Python list 会被当成
  `double precision[]`，必须显式转成 pgvector 类型（调试中踩过的坑）

### `src/notefind/qa.py`
RAG 问答编排：
- `retrieve()`：问题 → embedding → 向量检索
- `_format_context()`：把命中片段拼成 `[1] 路径（heading）\n内容` 格式
- `build_qa_chain()`：LangChain LCEL 链 `prompt | ChatOpenAI | StrOutputParser`，
  system prompt 要求**只根据资料回答、找不到就说找不到、末尾列引用**
- `ask()` 返回 `(答案, 引用列表)`

### `src/notefind/cli.py`
typer 入口，两个命令：
- `notefind sync`：全量增量同步，打印每文件进度 + 汇总统计
- `notefind ask "问题" [--show-context]`：回答 + 引用来源列表，
  `--show-context` 额外显示检索到的原文片段（调参用）

---

## `scripts/`（一次性脚本，非产品代码）

| 脚本 | 用途 |
|---|---|
| `check_schema.py` | 打印数据库实际表结构（排查文档与实际不一致时用） |
| `migrate_001.py` | 幂等补齐缺失列：`documents.mtime`、`chunks.heading`（已执行） |
| `selftest.py` | 自测 chunker 和 zim 解析 |
| `selftest_embed.py` | 自测 embedding 客户端（维度 1024 校验） |

## 已知注意事项

1. **表结构**：你手工建的表缺 `mtime`/`heading` 两列，已由 `migrate_001.py`
   补齐；`chunks` 还没有 `content_tsv`（第二步混合检索时再加）
2. **embedding 速度**：ollama 的 qwen3-embedding 在你机器上是纯 CPU 推理，
   全量入库会很慢；建议逐步扩大 `NOTE_DIRS`，或确认 GPU 可用后跑全量
3. **`.env` 不要提交**（含数据库密码），`.env.example` 是模板
