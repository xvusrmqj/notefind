import { useEffect, useRef, useState } from "react";
import { fetchSyncStatus, triggerSync, SyncStatus } from "./api";

export default function SyncPage() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await fetchSyncStatus();
        setStatus(s);
        // 运行中 1s 轮询，空闲 5s
        timer.current = setTimeout(poll, s.running ? 1000 : 5000);
      } catch (e) {
        setError(String(e));
        timer.current = setTimeout(poll, 5000);
      }
    };
    poll();
    return () => clearTimeout(timer.current);
  }, []);

  const trigger = async () => {
    try {
      await triggerSync();
      setError("");
    } catch (e) {
      setError(String(e));
    }
  };

  if (!status) return <div className="card muted">{error || "加载中…"}</div>;

  const pct =
    status.running && status.total
      ? Math.round(((status.current ?? 0) / status.total) * 100)
      : null;

  return (
    <>
      <div className="card">
        <div className="input-row">
          <button className="primary" onClick={trigger} disabled={status.running}>
            {status.running ? "同步进行中…" : "立即同步"}
          </button>
          {status.running && status.total != null && (
            <span className="muted" style={{ alignSelf: "center" }}>
              {status.current ?? 0} / {status.total}（{pct}%）
            </span>
          )}
        </div>
        {status.running && (
          <div className="progress-bar" style={{ marginTop: 12 }}>
            <div style={{ width: `${pct ?? 0}%` }} />
          </div>
        )}
        {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
      </div>

      <div className="card">
        <div className="stat-grid">
          <div className="stat">
            <div className="num">{status.stats.documents}</div>
            <div className="label">文档</div>
          </div>
          <div className="stat">
            <div className="num">{status.stats.chunks}</div>
            <div className="label">chunks</div>
          </div>
        </div>
      </div>

      {status.last_run && (
        <div className="card muted">
          上次同步：{new Date(status.last_run).toLocaleString()}
          {status.last_result && (
            <>
              {" ｜ "}
              扫描 {status.last_result.scanned} · 新增 {status.last_result.added} · 更新{" "}
              {status.last_result.updated} · 跳过 {status.last_result.skipped} · 删除{" "}
              {status.last_result.deleted} · 错误 {status.last_result.errors}
            </>
          )}
        </div>
      )}
    </>
  );
}
