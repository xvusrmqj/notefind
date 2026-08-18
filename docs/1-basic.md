# 第一步：基础版

目标：跑通最小闭环 —— 扫描笔记 → 入库 → 向量检索 → LLM 回答。

技术栈（建议）：Python + `psycopg` + `pgvector`。

## postgresql + pgvector
```sql
CREATE USER notefind WITH PASSWORD '123456';
CREATE DATABASE notefind OWNER notefind;
-- 需超级用户执行，且要在 notefind 库内
CREATE EXTENSION vector;
```

## 表结构
documents
    │
    │ 1:N
    ↓
chunks

```sql
-- ============================================================
-- documents
-- 一条记录对应一个本地笔记文件
-- ============================================================

CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,

    -- 文件的唯一标识
    file_path TEXT NOT NULL UNIQUE,

    -- 文件名
    file_name TEXT NOT NULL,

    -- 文件类型：obsidian / logseq / zim / markdown ...
    source_type TEXT NOT NULL,

    -- 文件原始内容的 SHA-256
    -- 用于判断文件是否发生变化
    content_hash TEXT NOT NULL,

    -- 文件修改时间
    -- mtime 未变则跳过 hash 计算，减少 IO
    mtime TIMESTAMPTZ NOT NULL
);


-- ============================================================
-- chunks
-- 一篇文档切分成多个 Chunk
-- 每个 Chunk 对应一个 Embedding
-- ============================================================

CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,

    -- 所属文档
    document_id BIGINT NOT NULL
        REFERENCES documents(id)
        ON DELETE CASCADE,

    -- Chunk 在文档中的顺序
    chunk_index INTEGER NOT NULL,

    -- Chunk 所属标题路径（如 "项目/notefind/设计"）
    -- 展示引用来源时使用
    heading TEXT,

    -- Chunk 原始文本
    -- RAG 检索后会把它交给 LLM
    content TEXT NOT NULL,

    -- Qwen3-Embedding 0.6B 的 1024 维向量
    embedding VECTOR(1024) NOT NULL,

    -- 同一个文档中，chunk_index 必须唯一
    UNIQUE (document_id, chunk_index)
);


-- ============================================================
-- HNSW 向量索引
-- 使用 Cosine Distance
-- ============================================================

CREATE INDEX idx_chunks_embedding_hnsw
ON chunks
USING hnsw (embedding vector_cosine_ops);
```

## 入库业务逻辑
```
扫描本地文件（先比对 mtime，未变则跳过）
      ↓
计算 SHA-256
      ↓
查询 documents.file_path
      ↓
┌─────────────────┐
│ 文件不存在？      │── YES → 新增 document + chunks
└─────────────────┘
      │
      NO
      ↓
┌─────────────────┐
│ 磁盘上已删除？    │── YES → 删除 document（cascade 清理 chunks）
└─────────────────┘
      │
      NO
      ↓
比较 content_hash
      ↓
┌─────────────────┐
│ hash 相同？      │── YES → 什么都不做
└─────────────────┘
      │
      NO
      ↓
删除旧 chunks
      ↓
重新 Chunk（按 Markdown 结构切分）
      ↓
重新 Embedding（批量，每批 32~64 条）
      ↓
插入新 chunks
      ↓
更新 content_hash / mtime
```

## Chunking 策略

- 按 Markdown 结构切分：标题层级 + 段落，而非固定字符数
- 目标 chunk 大小约 300~500 字符，超出时按段落再切
- 代码块保持完整，过长则整体作为一个 chunk
- 跳过 YAML front matter（可单独存入 metadata）
- 记录 chunk 所属标题路径到 `heading` 字段

## 检索流程（向量检索）

```
用户自然语言查询
      ↓
构造查询文本：加 instruction 前缀 "query: ..."
（Qwen3-Embedding 为非对称检索模型，查询侧需加前缀，文档侧不加）
      ↓
embedding(查询)
      ↓
向量 top-k 检索（cosine，k=10）
      ↓
（可选）按相似度阈值过滤 / 截断
      ↓
拼接 context + 查询 → LLM
      ↓
返回答案 + 引用来源（file_path + heading）
```

检索 SQL：

```sql
SELECT c.content, c.heading, d.file_path,
       1 - (c.embedding <=> :query_vec) AS similarity
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> :query_vec
LIMIT 10;
```

## 交付物

- `notefind sync` 命令：扫描 + 增量入库
- `notefind ask "问题"` 命令：向量检索 + LLM 回答（CLI 交互）
