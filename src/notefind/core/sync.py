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
from .parsers import ATTACH_MIME, extract_attachment, parse_file
from .scanner import ScannedFile, find_attachments, scan_dir, sha256_of


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
    referenced_by: list[int] | None = None,
) -> None:
    """单文档一个事务：新增或更新 document + chunks。"""
    mtime = datetime.fromtimestamp(sf.mtime, tz=timezone.utc)
    mime = ATTACH_MIME.get(sf.path.suffix.lower()) if sf.kind == "attachment" else None
    with conn.transaction():
        if existing_id is None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documents
                        (file_path, file_name, source_type, content_hash, mtime,
                         kind, mime_type, referenced_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        sf.file_path, sf.path.name, sf.source_type, content_hash, mtime,
                        sf.kind, mime, referenced_by,
                    ),
                )
                existing_id = cur.fetchone()[0]
        else:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE document_id = %s", (existing_id,))
                cur.execute(
                    """
                    UPDATE documents
                    SET file_name = %s, source_type = %s, content_hash = %s, mtime = %s,
                        kind = %s, mime_type = %s, referenced_by = %s
                    WHERE id = %s
                    """,
                    (
                        sf.path.name, sf.source_type, content_hash, mtime,
                        sf.kind, mime, referenced_by, existing_id,
                    ),
                )
        _insert_chunks(conn, existing_id, chunks, vectors)


def _attachment_chunks(sf: ScannedFile) -> list[Chunk]:
    """附件提取：PDF 逐页预切（页码写入 heading），再走通用切分。"""
    pages = extract_attachment(sf.path)
    if pages is None:
        raise ValueError(f"不支持的附件类型: {sf.path.suffix}")
    chunks: list[Chunk] = []
    idx = 0
    for page in pages:
        if not page.content:
            continue
        heading = f"p.{page.page}" if page.page is not None else None
        for c in split_markdown(page.content):
            chunks.append(
                Chunk(
                    chunk_index=idx,
                    heading=heading if heading else c.heading,
                    content=c.content,
                )
            )
            idx += 1
    return chunks


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

        # 1.5 附件发现：解析笔记中的显式引用（![[x.pdf]] / [a](x.docx) / zim {{x.pdf}}）
        attach_refs = find_attachments(scanned)
        for apath in attach_refs:
            p = Path(apath)
            scanned.append(
                ScannedFile(
                    path=p, source_type="attachment", mtime=p.stat().st_mtime,
                    kind="attachment",
                )
            )
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

                if sf.kind == "attachment":
                    chunks = _attachment_chunks(sf)
                else:
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

        # 4. 回填 referenced_by：附件 -> 引用它的笔记 document_id 列表
        #    （全量重算，能正确处理笔记增删引用链的情况）
        if attach_refs:
            with conn.cursor() as cur:
                cur.execute("SELECT id, file_path FROM documents WHERE kind = 'note'")
                path_to_id = {row[1]: row[0] for row in cur.fetchall()}
            for apath, note_paths in attach_refs.items():
                ids = sorted(
                    {path_to_id[str(p)] for p in note_paths if str(p) in path_to_id}
                )
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE documents SET referenced_by = %s WHERE file_path = %s",
                        (ids, apath),
                    )

    return stats


def _report(progress, idx: int, total: int, sf: ScannedFile, action: str) -> None:
    if progress is not None:
        progress(idx, total, sf, action)


def _flatten(paths) -> list[Path]:
    out: list[Path] = []
    for lst in paths:
        out.extend(lst)
    return out
