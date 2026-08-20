"""入库业务逻辑：扫描 → 增量同步 documents/chunks（docs/1-basic.md 流程图）。"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from psycopg import Connection
from psycopg.rows import dict_row

from .chunker import Chunk, split_markdown
from .config import Settings
from .db import get_pool
from .embedding import embed_documents_batched, make_embedder
from .parsers import parse_file
from .scanner import ScannedFile, scan_dir, sha256_of


@dataclass
class SyncStats:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"扫描 {self.scanned} | 新增 {self.added} | 更新 {self.updated} "
            f"| 跳过 {self.skipped} | 删除 {self.deleted} | 错误 {len(self.errors)}"
        )


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _load_db_state(conn: Connection) -> dict[str, dict]:
    """file_path -> {id, content_hash, mtime}"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, file_path, content_hash, mtime FROM documents")
        return {row["file_path"]: row for row in cur.fetchall()}


def _insert_chunks(
    conn: Connection, document_id: int, chunks: list[Chunk], vectors: list[list[float]]
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (document_id, chunk_index, heading, content, embedding)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (document_id, c.chunk_index, c.heading, c.content, v)
                for c, v in zip(chunks, vectors)
            ],
        )


def _upsert_document(
    conn: Connection,
    sf: ScannedFile,
    content_hash: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    existing_id: int | None,
) -> None:
    """单文档一个事务：新增或更新 document + chunks。"""
    mtime = datetime.fromtimestamp(sf.mtime, tz=timezone.utc)
    with conn.transaction():
        if existing_id is None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents (file_path, file_name, source_type, content_hash, mtime)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (sf.file_path, sf.path.name, sf.source_type, content_hash, mtime),
                )
                existing_id = cur.fetchone()[0]
        else:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE document_id = %s", (existing_id,))
                cur.execute(
                    """
                    UPDATE documents
                    SET file_name = %s, source_type = %s, content_hash = %s, mtime = %s
                    WHERE id = %s
                    """,
                    (sf.path.name, sf.source_type, content_hash, mtime, existing_id),
                )
        _insert_chunks(conn, existing_id, chunks, vectors)


def sync_all(settings: Settings, progress=None) -> SyncStats:
    """progress: 可选回调 (序号, 总数, ScannedFile, 动作)，用于 CLI 进度显示。"""
    stats = SyncStats()
    embedder = make_embedder(
        settings.embed_base_url, settings.embed_model, settings.embed_api_key
    )
    pool = get_pool()

    with pool.connection() as conn:
        db_state = _load_db_state(conn)

        # 1. 扫描所有目录
        scanned: list[ScannedFile] = []
        for note_dir in settings.note_dirs:
            scanned.extend(scan_dir(note_dir))
        stats.scanned = len(scanned)
        disk_paths = {sf.file_path for sf in scanned}

        # 2. 磁盘上已删除的文档 → 删除（cascade 清理 chunks）
        for file_path, row in db_state.items():
            if file_path not in disk_paths:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM documents WHERE id = %s", (row["id"],))
                stats.deleted += 1

        # 3. 逐文件增量处理
        total = len(scanned)
        for idx, sf in enumerate(scanned, 1):
            row = db_state.get(sf.file_path)
            action = "skip"
            try:
                # mtime 预过滤：未变则跳过 hash 计算
                if row is not None and row["mtime"] is not None:
                    db_mtime = row["mtime"]
                    if hasattr(db_mtime, "timestamp"):
                        db_mtime = db_mtime.timestamp()
                    if abs(db_mtime - sf.mtime) < 1e-6:
                        stats.skipped += 1
                        _report(progress, idx, total, sf, "skip")
                        continue

                content_hash = sha256_of(sf.path)
                if row is not None and row["content_hash"] == content_hash:
                    # hash 相同：仅刷新 mtime，不重建 chunks
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE documents SET mtime = %s WHERE id = %s",
                            (datetime.fromtimestamp(sf.mtime, tz=timezone.utc), row["id"]),
                        )
                    stats.skipped += 1
                    _report(progress, idx, total, sf, "skip(hash)")
                    continue

                parsed = parse_file(sf.path, sf.source_type)
                chunks = split_markdown(parsed.markdown)
                if not chunks:
                    # 空文档也记录，避免每次重扫
                    _upsert_document(conn, sf, content_hash, [], [], row["id"] if row else None)
                    stats.skipped += 1
                    _report(progress, idx, total, sf, "empty")
                    continue

                vectors = embed_documents_batched(
                    embedder,
                    [c.content for c in chunks],
                    settings.embed_batch_size,
                    settings.embed_pause_ms,
                )
                _upsert_document(
                    conn, sf, content_hash, chunks, vectors, row["id"] if row else None
                )
                if row is None:
                    stats.added += 1
                    action = "add"
                else:
                    stats.updated += 1
                    action = "update"
            except Exception as e:  # noqa: BLE001
                stats.errors.append(f"{sf.file_path}: {e}")
                action = "error"
            finally:
                _report(progress, idx, total, sf, action)

    return stats


def _report(progress, idx: int, total: int, sf: ScannedFile, action: str) -> None:
    if progress is not None:
        progress(idx, total, sf, action)
