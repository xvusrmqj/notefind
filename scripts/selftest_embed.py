"""自测：embedding 客户端（查询前缀 + 批量文档）。"""
from notefind.config import load_settings
from notefind.embedding import embed_documents_batched, embed_query, make_embedder

s = load_settings()
e = make_embedder(s.embed_base_url, s.embed_model, s.embed_api_key)

q = embed_query(e, "如何配置数据库")
docs = embed_documents_batched(e, ["文档一内容", "文档二内容"], 2)
print("query dim:", len(q))
print("docs dims:", [len(v) for v in docs])
assert len(q) == 1024 and all(len(v) == 1024 for v in docs)
print("embedding OK")
