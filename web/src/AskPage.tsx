import { useState } from "react";
import { askStream, Citation, Mode } from "./api";

const MODES: { key: Mode; label: string }[] = [
  { key: "hybrid", label: "混合" },
  { key: "vector", label: "向量" },
  { key: "fts", label: "全文" },
];

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>("hybrid");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const submit = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setError("");
    setAnswer("");
    setCitations([]);
    setExpanded(null);
    await askStream(question, mode, {
      onCitations: setCitations,
      onDelta: (t) => setAnswer((a) => a + t),
      onDone: () => setBusy(false),
      onError: (m) => {
        setError(m);
        setBusy(false);
      },
    });
  };

  return (
    <>
      <div className="card">
        <div className="input-row">
          <input
            type="text"
            placeholder="用自然语言提问，例如：部署流程里数据库备份是怎么做的？"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
            {MODES.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
          <button className="primary" onClick={submit} disabled={busy || !question.trim()}>
            {busy ? "回答中…" : "提问"}
          </button>
        </div>
      </div>

      {error && <div className="card error">{error}</div>}

      {answer && (
        <div className="card">
          <div className="answer">{answer}</div>
        </div>
      )}

      {citations.length > 0 && (
        <div className="card">
          <div className="muted" style={{ marginBottom: 8 }}>
            引用来源（点击展开原文）
          </div>
          {citations.map((c, i) => (
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
              {expanded === c.chunk_id && <div className="full">{c.content}</div>}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
