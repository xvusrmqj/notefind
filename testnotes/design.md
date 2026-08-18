# 项目 A 设计文档

本项目是一个本地笔记搜索引擎，使用 RAG 技术。

## 数据库

使用 PostgreSQL + pgvector 扩展存储向量。
documents 表存文件元信息，chunks 表存切分后的片段和 1024 维 embedding。

## 检索

查询时加 "query: " 前缀，用 cosine 距离做 top-k 检索。

```python
def search(query_vec, k=10):
    return vector_search(query_vec, k)
```

### 后续计划

- 混合检索（RRF 融合）
- Web UI
