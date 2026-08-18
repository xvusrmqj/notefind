"""按 docs/1-basic.md 补齐缺失列（幂等）。"""
import psycopg

DDL = [
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS mtime TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS heading TEXT",
]

conn = psycopg.connect("postgresql://notefind:123456@localhost:5432/notefind")
for stmt in DDL:
    conn.execute(stmt)
    print("OK:", stmt)
conn.commit()
