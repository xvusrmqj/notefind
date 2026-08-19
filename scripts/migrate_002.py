"""第二步混合检索迁移：chunks.content_tsv 生成列 + GIN 索引（幂等）。

前置：已安装 pg_jieba 扩展（见 docs/2-hybrid-search.md）。
注意：pg_jieba 提供的 text search 配置名为 jiebacfg。
"""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://notefind:123456@localhost:5432/notefind"
)

TSV_CONFIG = "jiebacfg"

DDL = [
    # 全文检索生成列（jieba 分词）
    (
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv "
        "TSVECTOR GENERATED ALWAYS AS "
        f"(to_tsvector('{TSV_CONFIG}', content)) STORED"
    ),
    # GIN 索引
    (
        "CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv "
        "ON chunks USING gin (content_tsv)"
    ),
]


def main() -> None:
    conn = psycopg.connect(DSN)
    try:
        # 校验 pg_jieba 已启用
        cur = conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'pg_jieba'"
        )
        if cur.fetchone() is None:
            raise SystemExit(
                "错误: pg_jieba 扩展未启用，请先安装（见 docs/2-hybrid-search.md）"
            )
        # 校验分词配置存在
        cur = conn.execute(
            "SELECT 1 FROM pg_ts_config WHERE cfgname = %s", (TSV_CONFIG,)
        )
        if cur.fetchone() is None:
            raise SystemExit(f"错误: text search 配置 {TSV_CONFIG!r} 不存在")

        for stmt in DDL:
            conn.execute(stmt)
            print("OK:", stmt)
        conn.commit()
        print(f"\n使用的分词配置: {TSV_CONFIG}")
        print("提示: 应用侧 .env 需设置 TSV_CONFIG=jiebacfg")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
