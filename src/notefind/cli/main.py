"""CLI 入口：notefind sync / ask / serve。"""

from __future__ import annotations

import typer

from ..core.config import load_settings
from ..core.db import close_pool, init_pool
from ..core.retriever import RetrievalMode

app = typer.Typer(help="notefind: 本地笔记 RAG 搜索", no_args_is_help=True)


@app.command()
def sync() -> None:
    """扫描笔记目录并增量入库。"""
    settings = load_settings()
    init_pool(settings.database_url)
    try:
        from ..core.sync import sync_all

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
    retrieval: RetrievalMode = typer.Option(
        RetrievalMode.hybrid.value,
        "--retrieval",
        help="检索模式: hybrid（RRF 融合）/ vector（纯向量）/ fts（纯全文）",
    ),
) -> None:
    """混合检索 + LLM 回答。"""
    settings = load_settings()
    init_pool(settings.database_url)
    try:
        from ..core.qa import ask as do_ask

        answer, hits = do_ask(settings, question, mode=retrieval)
        typer.echo(answer)
        typer.echo()
        typer.secho("── 引用来源 ──", bold=True)
        if not hits:
            typer.echo("（无）")
        for i, h in enumerate(hits, 1):
            heading = f" › {h.heading}" if h.heading else ""
            kind_tag = "[附件] " if h.kind == "attachment" else ""
            typer.echo(
                f"[{i}] {kind_tag}{h.file_path}{heading}  (score {h.score:.3f})"
            )
            if show_context:
                typer.echo(f"    {h.content[:200]}...")
    finally:
        close_pool()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="监听地址（默认仅本机）"),
    port: int = typer.Option(8000, help="监听端口"),
) -> None:
    """启动 Web UI（FastAPI，前端构建产物自动托管）。"""
    import uvicorn

    uvicorn.run("notefind.webapi.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
