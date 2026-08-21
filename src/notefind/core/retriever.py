"""混合检索：向量 + 全文（RRF 融合），可单路退化（docs/2-hybrid-search.md）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from .db import get_pool


class RetrievalMode(str, Enum):
    hybrid = "hybrid"
    vector = "vector"
    fts = "fts"


# RRF 融合（常数 60），双路各取 top-k
HYBRID_SQL = """
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
SELECT c.id AS chunk_id, c.content, c.heading, d.file_path,
       d.kind, d.mime_type, d.referenced_by,
       COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + f.rank), 0) AS score
FROM vec v
FULL JOIN fts f USING (id)
JOIN chunks c ON c.id = COALESCE(v.id, f.id)
JOIN documents d ON d.id = c.document_id
ORDER BY score DESC
LIMIT %(k)s
"""

VECTOR_SQL = """
SELECT c.id AS chunk_id, c.content, c.heading, d.file_path,
       d.kind, d.mime_type, d.referenced_by,
       1 - (c.embedding <=> %(query_vec)s::vector) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> %(query_vec)s::vector
LIMIT %(k)s
"""

FTS_SQL = """
SELECT c.id AS chunk_id, c.content, c.heading, d.file_path,
       d.kind, d.mime_type, d.referenced_by,
       ts_rank(c.content_tsv, query) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id,
     plainto_tsquery(%(cfg)s::regconfig, %(q)s) AS query
WHERE c.content_tsv @@ query
ORDER BY score DESC
LIMIT %(k)s
"""


@dataclass
class SearchHit:
    chunk_id: int
    content: str
    heading: str | None
    file_path: str
    score: float
    kind: str = "note"  # 'note' | 'attachment'
    mime_type: str | None = None
    referenced_by: list[int] | None = None  # 引用该附件的笔记 document_id


def hybrid_search(
    query_vec: list[float],
    query_text: str,
    k: int = 10,
    tsv_config: str = "jiebacfg",
    mode: RetrievalMode = RetrievalMode.hybrid,
) -> list[SearchHit]:
    """混合检索：RRF 融合向量与全文两路；mode 可切换单路。"""
    params: dict = {"k": k, "cfg": tsv_config, "q": query_text}
    if mode is not RetrievalMode.fts:
        params["query_vec"] = query_vec
    sql = {
        RetrievalMode.hybrid: HYBRID_SQL,
        RetrievalMode.vector: VECTOR_SQL,
        RetrievalMode.fts: FTS_SQL,
    }[mode]

    with get_pool().connection() as conn:
        register_vector(conn)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return [
                SearchHit(
                    chunk_id=r["chunk_id"],
                    content=r["content"],
                    heading=r["heading"],
                    file_path=r["file_path"],
                    score=float(r["score"]),
                    kind=r.get("kind") or "note",
                    mime_type=r.get("mime_type"),
                    referenced_by=list(r["referenced_by"]) if r.get("referenced_by") else None,
                )
                for r in cur.fetchall()
            ]
