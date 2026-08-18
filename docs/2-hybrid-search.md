# 第二步：混合检索（Hybrid Search）

目标：在向量检索基础上增加全文检索（tsvector），双路召回 + RRF 融合，
提升专有名词、文件名、标签等关键词查询的召回质量。

## 表结构变更

```sql
-- 全文检索生成列
ALTER TABLE chunks
ADD COLUMN content_tsv TSVECTOR GENERATED ALWAYS AS
    (to_tsvector('simple', content)) STORED;

-- GIN 索引
CREATE INDEX idx_chunks_content_tsv
ON chunks
USING gin (content_tsv);
```

> 注：中文全文检索 `simple` 分词效果有限，可后续考虑 `pg_jieba` / `zhparser` 扩展，
> 或由应用层分词后拼接 `to_tsquery`。

## 检索流程

```
用户自然语言查询
      ↓
构造查询文本：加 instruction 前缀 "query: ..."
      ↓
embedding(查询)
      ↓
混合检索：
  ├─ 向量 top-k（cosine，k=10）
  └─ 全文 top-k（ts_rank，k=10）
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
        ORDER BY embedding <=> :query_vec
    ) AS rank
    FROM chunks
    ORDER BY embedding <=> :query_vec
    LIMIT 10
),
fts AS (
    SELECT id, ROW_NUMBER() OVER (
        ORDER BY ts_rank(content_tsv, :query) DESC
    ) AS rank
    FROM chunks
    WHERE content_tsv @@ plainto_tsquery('simple', :query)
    ORDER BY ts_rank(content_tsv, :query) DESC
    LIMIT 10
)
SELECT c.id, c.content, c.heading, d.file_path,
       COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + f.rank), 0) AS score
FROM vec v
FULL JOIN fts f USING (id)
JOIN chunks c ON c.id = COALESCE(v.id, f.id)
JOIN documents d ON d.id = c.document_id
ORDER BY score DESC;
```

## 交付物

- `notefind ask` 升级为混合检索，CLI 增加 `--no-fts` / `--no-vec` 开关便于对比效果
- （可选）检索结果评分展示，便于调参（k、RRF 常数 60）
