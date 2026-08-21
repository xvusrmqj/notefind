"""FastAPI 应用：路由 + SSE 问答 + 静态托管。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import load_settings
from ..core.db import close_pool, init_pool
from ..core.qa import retrieve, ask_stream
from ..core.retriever import RetrievalMode, SearchHit
from .schemas import (
    AskRequest,
    ChunkItem,
    Citation,
    DocumentDetail,
    DocumentItem,
    DocumentListResponse,
    SearchRequest,
    SearchResponse,
    SyncResult,
    SyncStatus,
    SyncStats,
)
from .sync_manager import SyncManager

# 本地 LLM 单并发：ask 请求排队执行
_ask_semaphore = asyncio.Semaphore(1)

_settings = load_settings()
sync_manager = SyncManager(_settings)

# 前端构建产物（项目根 web/dist）；开发模式由 Vite dev server 代理
_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool(_settings.database_url)
    yield
    close_pool()


app = FastAPI(title="notefind", lifespan=lifespan)


def _mode(raw: str) -> RetrievalMode:
    try:
        return RetrievalMode(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"非法检索模式: {raw}") from None


def _citation(h: SearchHit) -> Citation:
    return Citation(
        chunk_id=h.chunk_id,
        file_path=h.file_path,
        heading=h.heading,
        score=h.score,
        content=h.content,
        kind=h.kind,
        mime_type=h.mime_type,
        referenced_by=h.referenced_by,
    )


# ── 同步管理 ──────────────────────────────────────────────


@app.post("/api/sync", status_code=202)
async def trigger_sync() -> dict:
    if not sync_manager.start():
        raise HTTPException(status_code=409, detail="同步已在进行中")
    return {"started": True}


@app.get("/api/sync/status", response_model=SyncStatus)
def sync_status() -> SyncStatus:
    stats = sync_manager.db_stats()
    last = sync_manager.last_result
    return SyncStatus(
        running=sync_manager.running,
        current=sync_manager.current,
        total=sync_manager.total,
        last_run=sync_manager.last_run,
        last_result=(
            SyncResult(
                scanned=last.scanned,
                added=last.added,
                updated=last.updated,
                skipped=last.skipped,
                deleted=last.deleted,
                errors=len(last.errors),
            )
            if last
            else None
        ),
        stats=SyncStats(**stats),
    )


# ── 搜索 / 问答 ───────────────────────────────────────────


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    hits = retrieve(_settings, req.query, mode=_mode(req.mode))
    return SearchResponse(hits=[_citation(h) for h in hits])


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/ask")
async def ask(req: AskRequest) -> StreamingResponse:
    async def gen():
        async with _ask_semaphore:
            try:
                hits, tokens = await asyncio.to_thread(
                    ask_stream, _settings, req.query, _mode(req.mode)
                )
                yield _sse("citations", [_citation(h).model_dump() for h in hits])
                # chain.stream() 是同步生成器，逐 token 放回事件循环
                while True:
                    token = await asyncio.to_thread(next, tokens, None)
                    if token is None:
                        break
                    yield _sse("delta", {"text": token})
                yield _sse("done", {})
            except Exception as e:  # noqa: BLE001
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── 文档浏览 ──────────────────────────────────────────────


@app.get("/api/documents", response_model=DocumentListResponse)
def list_documents(
    offset: int = 0, limit: int = 50, q: str = ""
) -> DocumentListResponse:
    from ..core.db import get_pool

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            if q:
                cur.execute(
                    "SELECT count(*) FROM documents WHERE file_path ILIKE %s",
                    (f"%{q}%",),
                )
            else:
                cur.execute("SELECT count(*) FROM documents")
            total = cur.fetchone()[0]
            sql = """
            SELECT d.id, d.file_path, d.file_name, d.source_type, d.mtime,
                   count(c.id) AS chunk_count
            FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
            """
            params: list = []
            if q:
                sql += " WHERE d.file_path ILIKE %s"
                params.append(f"%{q}%")
            sql += " GROUP BY d.id ORDER BY d.mtime DESC NULLS LAST LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            cur.execute(sql, params)
            rows = cur.fetchall()
    return DocumentListResponse(
        total=total,
        items=[
            DocumentItem(
                id=r[0],
                file_path=r[1],
                file_name=r[2],
                source_type=r[3],
                mtime=r[4],
                chunk_count=r[5],
            )
            for r in rows
        ],
    )


@app.get("/api/documents/{doc_id}", response_model=DocumentDetail)
def document_detail(doc_id: int) -> DocumentDetail:
    from ..core.db import get_pool

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_path, file_name, source_type, mtime "
                "FROM documents WHERE id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="文档不存在")
            cur.execute(
                "SELECT id, chunk_index, heading, content FROM chunks "
                "WHERE document_id = %s ORDER BY chunk_index",
                (doc_id,),
            )
            chunks = [
                ChunkItem(id=c[0], chunk_index=c[1], heading=c[2], content=c[3])
                for c in cur.fetchall()
            ]
    return DocumentDetail(
        id=row[0],
        file_path=row[1],
        file_name=row[2],
        source_type=row[3],
        mtime=row[4],
        chunks=chunks,
    )


# ── 静态托管（生产模式：web/dist 存在时挂载）──────────────

if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
