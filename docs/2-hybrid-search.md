# 第二步：混合检索（Hybrid Search）

目标：在向量检索基础上增加全文检索（tsvector），双路召回 + RRF 融合，
提升专有名词、文件名、标签等关键词查询的召回质量。

中文分词统一使用 **pg_jieba** 扩展（不做其它兜底）。

## 前置：安装 pg_jieba

pg_jieba 需在 PostgreSQL 服务器侧安装（apt 包名视 PG 版本而定，如 `postgresql-16-jieba`；
无预编译包时需源码编译），然后执行：

```sql
CREATE EXTENSION IF NOT EXISTS pg_jieba;
```

## 表结构变更（scripts/migrate_002.py，幂等）

```sql
-- 全文检索生成列（jieba 分词；注意 pg_jieba 的配置名是 jiebacfg）
ALTER TABLE chunks
ADD COLUMN content_tsv TSVECTOR GENERATED ALWAYS AS
    (to_tsvector('jiebacfg', content)) STORED;

-- GIN 索引
CREATE INDEX idx_chunks_content_tsv
ON chunks
USING gin (content_tsv);
```

> 注：生成列表达式不可 ALTER；若列已存在但分词配置不同，需 DROP COLUMN 后重新添加（数据自动重算）。

## 检索流程

```
用户自然语言查询
      ↓
构造查询文本：加 instruction 前缀 "query: ..."
      ↓
embedding(查询)
      ↓
混合检索（hybrid_search，--retrieval 可切换单路）：
  ├─ 向量 top-k（cosine，k=10）      --retrieval vector 时仅此路
  └─ 全文 top-k（ts_rank，k=10）      --retrieval fts 时仅此路
      ↓
RRF 融合两路结果（去重）
      ↓
（可选）按相似度阈值过滤 / 截断
      ↓
拼接 context + 查询 → LLM
      ↓
返回答案 + 引用来源（file_path + heading）
```

## RRF（Reciprocal Rank Fusion）示例 SQL

```sql
WITH vec AS (
    SELECT id, ROW_NUMBER() OVER (
        ORDER BY embedding <=> %(query_vec)s::vector
    ) AS rank
    FROM chunks
    ORDER BY embedding <=> %(query_vec)s::vector
    LIMIT %(k)s
),
fts AS (
    SELECT id, ROW_NUMBER() OVER (
        ORDER BY ts_rank(content_tsv, query) DESC
    ) AS rank
    FROM chunks,
         plainto_tsquery(%(cfg)s::regconfig, %(q)s) AS query
    WHERE content_tsv @@ query
    ORDER BY ts_rank(content_tsv, query) DESC
    LIMIT %(k)s
)
SELECT c.id, c.content, c.heading, d.file_path,
       COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + f.rank), 0) AS score
FROM vec v
FULL JOIN fts f USING (id)
JOIN chunks c ON c.id = COALESCE(v.id, f.id)
JOIN documents d ON d.id = c.document_id
ORDER BY score DESC;
```

> 参数：`cfg` 来自 `TSV_CONFIG`（默认 `jiebacfg`），`k` 来自 `TOP_K`（默认 10）。
> `--retrieval vector` 时退化为纯向量 SQL，`--retrieval fts` 时退化为纯全文 SQL（`SearchHit.similarity` 改为通用 `score`）。

## 配置

```dotenv
# 全文检索分词配置，须与迁移脚本使用的配置一致
# pg_jieba 提供的配置: jiebacfg / jiebaqry / jiebamp / jiebahmm
TSV_CONFIG=jiebacfg
```

## 交付物

- `scripts/migrate_002.py`：建 content_tsv 生成列（jieba）+ GIN 索引（幂等）
- `scripts/check_schema.py`：校验 content_tsv 列与 GIN 索引
- `src/notefind/retriever.py`：`hybrid_search()`（RRF 融合 + 单路退化）
- `notefind ask` 升级为混合检索，CLI 增加 `--retrieval hybrid|vector|fts` 选项便于对比效果
- 引用行展示 RRF score（保留 3 位小数），便于调参（k、RRF 常数 60）

## 验证

```sh
uv run python scripts/migrate_002.py    # 建列 + 索引
uv run python scripts/check_schema.py   # 校验 schema

# 对比三路召回效果
uv run notefind ask "备份" --retrieval vector  # 纯向量
uv run notefind ask "备份" --retrieval fts     # 纯全文
uv run notefind ask "备份" --retrieval hybrid  # 混合（RRF，默认）

# 英文专名/文件名查询验证 FTS 路提升（如 RRF、excalidraw）
uv run python scripts/selftest.py      # 端到端不回归
```
