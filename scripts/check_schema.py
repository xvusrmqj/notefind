"""检查数据库实际表结构。"""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://notefind:123456@localhost:5432/notefind"
)

conn = psycopg.connect(DSN)
for t in ("documents", "chunks"):
    cur = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name='{t}' ORDER BY ordinal_position"
    )
    print(t, ":", cur.fetchall())

# 第二步：混合检索相关校验
cur = conn.execute(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_name='chunks' AND column_name='content_tsv'"
)
assert cur.fetchone(), "缺少 chunks.content_tsv（运行 scripts/migrate_002.py）"

cur = conn.execute(
    "SELECT 1 FROM pg_indexes "
    "WHERE tablename='chunks' AND indexname='idx_chunks_content_tsv'"
)
assert cur.fetchone(), "缺少 GIN 索引 idx_chunks_content_tsv"

cur = conn.execute("SELECT 1 FROM pg_extension WHERE extname='pg_jieba'")
assert cur.fetchone(), "缺少 pg_jieba 扩展"

# 第四步：附件字段校验
for col in ("kind", "mime_type", "referenced_by"):
    cur = conn.execute(
        "SELECT 1 FROM information_schema.columns "
        f"WHERE table_name='documents' AND column_name='{col}'"
    )
    assert cur.fetchone(), f"缺少 documents.{col}（运行 scripts/migrate_003.py）"

print("schema 校验通过：content_tsv + GIN 索引 + pg_jieba + 附件字段均就绪")
