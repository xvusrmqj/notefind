import { useState } from "react";
import { search, Citation, Mode } from "./api";

const MODES: { key: Mode; label: string }[] = [
  { key: "hybrid", label: "混合 (RRF)" },
  { key: "vector", label: "向量" },
  { key: "fts", label: "全文" },
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("hybrid");
  const [k, setK] = useState(10);
  const [hits, setHits] = useState<Citation[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const submit = async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      setHits(await search(query, mode, k));
    } catch (e) {
      setError(String(e));
      setHits(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card">
        <div className="input-row">
          <input
            type="text"
            placeholder="关键词或自然语言检索（不经过 LLM）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
            {MODES.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
          <select value={k} onChange={(e) => setK(Number(e.target.value))}>
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>
                top {n}
              </option>
            ))}
          </select>
          <button className="primary" onClick={submit} disabled={busy || !query.trim()}>
            {busy ? "检索中…" : "搜索"}
          </button>
        </div>
      </div>

      {error && <div className="card error">{error}</div>}

      {hits && (
        <div className="card">
          <div className="muted" style={{ marginBottom: 8 }}>
            共 {hits.length} 条结果（点击标题展开原文）
          </div>
          {hits.map((c, i) => (
            <div className="hit" key={c.chunk_id}>
              <div className="meta">
                <span
                  className="source"
                  onClick={() => setExpanded(expanded === c.chunk_id ? null : c.chunk_id)}
                >
                  [{i + 1}] {c.file_path}
                  {c.heading ? ` › ${c.heading}` : ""}
                </span>
                <span>score {c.score.toFixed(3)}</span>
              </div>
              <div className="content">{c.content.slice(0, 200)}…</div>
              {expanded === c.chunk_id && <div className="full">{c.content}</div>}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
