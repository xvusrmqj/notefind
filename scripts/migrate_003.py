"""第四步附件向量化迁移：documents 加 kind / mime_type / referenced_by（幂等）。

- kind: 'note' | 'attachment'（存量行默认 'note'）
- mime_type: 附件的 MIME 类型（笔记为 NULL）
- referenced_by: 引用该附件的笔记 document_id 列表（BIGINT[]，用于溯源展示）
"""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://notefind:123456@localhost:5432/notefind"
)

DDL = [
    (
        "ALTER TABLE documents "
        "ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'note'"
    ),
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS mime_type TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS referenced_by BIGINT[]",
]


def main() -> None:
    conn = psycopg.connect(DSN)
    try:
        for stmt in DDL:
            conn.execute(stmt)
            print("OK:", stmt)
        conn.commit()
        print("\n附件字段迁移完成：kind / mime_type / referenced_by")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
