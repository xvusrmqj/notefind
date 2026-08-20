import { useEffect, useState } from "react";
import { fetchDocument, fetchDocuments, DocumentItem, DocumentDetail } from "./api";

const PAGE_SIZE = 20;

export default function DocsPage() {
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDocuments(offset, PAGE_SIZE, q)
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((e) => setError(String(e)));
  }, [offset, q]);

  const open = async (id: number) => {
    if (detail?.id === id) {
      setDetail(null);
      return;
    }
    try {
      setDetail(await fetchDocument(id));
    } catch (e) {
      setError(String(e));
    }
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <>
      <div className="card">
        <div className="input-row">
          <input
            type="text"
            placeholder="按路径过滤…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </div>
      </div>

      {error && <div className="card error">{error}</div>}

      <div className="card">
        <div className="muted" style={{ marginBottom: 8 }}>
          共 {total} 个文档
        </div>
        {items.map((d) => (
          <div key={d.id}>
            <div className="doc-item" onClick={() => open(d.id)}>
              <span className="name">{d.file_path}</span>
              <span className="info">
                {d.source_type} · {d.chunk_count} chunks
              </span>
            </div>
            {detail?.id === d.id && (
              <div style={{ margin: "4px 0 12px" }}>
                {detail.chunks.map((c) => (
                  <div className="hit" key={c.id}>
                    <div className="meta">
                      <span>
                        #{c.chunk_index}
                        {c.heading ? ` › ${c.heading}` : ""}
                      </span>
                    </div>
                    <div className="content">{c.content}</div>
                  </div>
                ))}
                {detail.chunks.length === 0 && (
                  <div className="muted">（无 chunks：空文档）</div>
                )}
              </div>
            )}
          </div>
        ))}
        <div className="pager">
          <button
            className="primary"
            disabled={page <= 1}
            onClick={() => setOffset((offset) => offset - PAGE_SIZE)}
          >
            上一页
          </button>
          <span className="muted">
            {page} / {pages}
          </span>
          <button
            className="primary"
            disabled={page >= pages}
            onClick={() => setOffset((offset) => offset + PAGE_SIZE)}
          >
            下一页
          </button>
        </div>
      </div>
    </>
  );
}
