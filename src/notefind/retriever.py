"""向量检索：cosine top-k（docs/1-basic.md 检索 SQL）。"""

from __future__ import annotations

from dataclasses import dataclass

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .db import get_pool

SEARCH_SQL = """
SELECT c.content, c.heading, d.file_path,
       1 - (c.embedding <=> %(query_vec)s::vector) AS similarity
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> %(query_vec)s::vector
LIMIT %(k)s
"""


@dataclass
class SearchHit:
    content: str
    heading: str | None
    file_path: str
    similarity: float


def vector_search(query_vec: list[float], k: int = 10) -> list[SearchHit]:
    with get_pool().connection() as conn:
        register_vector(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(SEARCH_SQL, {"query_vec": query_vec, "k": k})
            return [
                SearchHit(
                    content=r["content"],
                    heading=r["heading"],
                    file_path=r["file_path"],
                    similarity=float(r["similarity"]),
                )
                for r in cur.fetchall()
            ]
