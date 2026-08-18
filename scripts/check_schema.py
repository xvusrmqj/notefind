"""检查数据库实际表结构。"""
import psycopg

conn = psycopg.connect("postgresql://notefind:123456@localhost:5432/notefind")
for t in ("documents", "chunks"):
    cur = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name='{t}' ORDER BY ordinal_position"
    )
    print(t, ":", cur.fetchall())
