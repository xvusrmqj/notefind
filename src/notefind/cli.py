"""CLI 入口：notefind sync / notefind ask。"""

from __future__ import annotations

import typer

from .config import load_settings
from .db import close_pool, init_pool

app = typer.Typer(help="notefind: 本地笔记 RAG 搜索", no_args_is_help=True)


@app.command()
def sync() -> None:
    """扫描笔记目录并增量入库。"""
    settings = load_settings()
    init_pool(settings.database_url)
    try:
        from .sync import sync_all

        def _progress(idx: int, total: int, sf, action: str) -> None:
            typer.echo(f"[{idx}/{total}] {action:10s} {sf.file_path}")

        stats = sync_all(settings, progress=_progress)
        typer.echo(stats.summary())
        for err in stats.errors:
            typer.secho(f"  错误: {err}", fg=typer.colors.RED)
    finally:
        close_pool()


@app.command()
def ask(
    question: str = typer.Argument(..., help="自然语言问题"),
    show_context: bool = typer.Option(
        False, "--show-context", help="同时显示检索到的片段"
    ),
) -> None:
    """向量检索 + LLM 回答。"""
    settings = load_settings()
    init_pool(settings.database_url)
    try:
        from .qa import ask as do_ask

        answer, hits = do_ask(settings, question)
        typer.echo(answer)
        typer.echo()
        typer.secho("── 引用来源 ──", bold=True)
        if not hits:
            typer.echo("（无）")
        for i, h in enumerate(hits, 1):
            heading = f" › {h.heading}" if h.heading else ""
            typer.echo(
                f"[{i}] {h.file_path}{heading}  (相似度 {h.similarity:.3f})"
            )
            if show_context:
                typer.echo(f"    {h.content[:200]}...")
    finally:
        close_pool()


if __name__ == "__main__":
    app()
