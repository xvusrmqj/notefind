"""后台同步任务管理：单实例运行，内存维护进度与统计。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..core.config import Settings
from ..core.db import get_pool
from ..core.sync import SyncStats, sync_all


class SyncManager:
    """同一时刻只允许一个同步任务；状态存内存供 /api/sync/status 查询。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._task: asyncio.Task | None = None
        self.running = False
        self.current: int | None = None
        self.total: int | None = None
        self.last_run: datetime | None = None
        self.last_result: SyncStats | None = None

    def start(self) -> bool:
        """启动同步；已在运行返回 False。"""
        if self.running:
            return False
        self.running = True
        self.current = None
        self.total = None
        self._task = asyncio.create_task(self._run())
        return True

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()

        def progress(idx: int, total: int, sf, action: str) -> None:
            # 在工作线程中被调用，仅做简单赋值（GIL 下安全）
            self.current = idx
            self.total = total

        try:
            stats = await asyncio.to_thread(
                sync_all, self._settings, progress
            )
            self.last_run = datetime.now(tz=timezone.utc)
            self.last_result = stats
        except Exception:  # noqa: BLE001
            self.last_run = datetime.now(tz=timezone.utc)
            self.last_result = SyncStats(errors=["同步任务异常中断"])
        finally:
            self.running = False
            self.current = None
            self.total = None
            self._task = None

    def db_stats(self) -> dict[str, int]:
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM documents")
                documents = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM chunks")
                chunks = cur.fetchone()[0]
        return {"documents": documents, "chunks": chunks}
