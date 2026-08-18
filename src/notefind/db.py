"""psycopg 连接池 + pgvector 注册。"""

from __future__ import annotations

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool(dsn: str) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=4,
            open=True,
            configure=register_vector,
        )
    return _pool


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("连接池未初始化，请先调用 init_pool()")
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
