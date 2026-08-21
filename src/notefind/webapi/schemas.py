"""API 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"  # hybrid | vector | fts
    k: int = Field(default=10, ge=1, le=50)


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "hybrid"


class Citation(BaseModel):
    chunk_id: int
    file_path: str
    heading: str | None = None
    score: float
    content: str
    kind: str = "note"  # 'note' | 'attachment'
    mime_type: str | None = None
    referenced_by: list[int] | None = None  # 引用该附件的笔记 document_id


class SearchResponse(BaseModel):
    hits: list[Citation]


class SyncResult(BaseModel):
    scanned: int
    added: int
    updated: int
    skipped: int
    deleted: int
    errors: int


class SyncStats(BaseModel):
    documents: int
    chunks: int


class SyncStatus(BaseModel):
    running: bool
    current: int | None = None
    total: int | None = None
    last_run: datetime | None = None
    last_result: SyncResult | None = None
    stats: SyncStats


class DocumentItem(BaseModel):
    id: int
    file_path: str
    file_name: str
    source_type: str
    mtime: datetime | None = None
    chunk_count: int


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentItem]


class ChunkItem(BaseModel):
    id: int
    chunk_index: int
    heading: str | None
    content: str


class DocumentDetail(BaseModel):
    id: int
    file_path: str
    file_name: str
    source_type: str
    mtime: datetime | None = None
    chunks: list[ChunkItem]
