export type Mode = "hybrid" | "vector" | "fts";

export interface Citation {
  chunk_id: number;
  file_path: string;
  heading: string | null;
  score: number;
  content: string;
  kind?: "note" | "attachment";
  mime_type?: string | null;
  referenced_by?: number[] | null;
}

export interface SyncStatus {
  running: boolean;
  current: number | null;
  total: number | null;
  last_run: string | null;
  last_result: {
    scanned: number;
    added: number;
    updated: number;
    skipped: number;
    deleted: number;
    errors: number;
  } | null;
  stats: { documents: number; chunks: number };
}

export interface DocumentItem {
  id: number;
  file_path: string;
  file_name: string;
  source_type: string;
  mtime: string | null;
  chunk_count: number;
}

export interface ChunkItem {
  id: number;
  chunk_index: number;
  heading: string | null;
  content: string;
}

export interface DocumentDetail extends DocumentItem {
  chunks: ChunkItem[];
}

export async function search(
  query: string,
  mode: Mode,
  k: number,
): Promise<Citation[]> {
  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode, k }),
  });
  if (!res.ok) throw new Error(`搜索失败: ${res.status}`);
  const data = await res.json();
  return data.hits;
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const res = await fetch("/api/sync/status");
  if (!res.ok) throw new Error(`获取同步状态失败: ${res.status}`);
  return res.json();
}

export async function triggerSync(): Promise<void> {
  const res = await fetch("/api/sync", { method: "POST" });
  if (res.status === 409) throw new Error("同步已在进行中");
  if (!res.ok) throw new Error(`触发同步失败: ${res.status}`);
}

export async function fetchDocuments(
  offset: number,
  limit: number,
  q: string,
): Promise<{ total: number; items: DocumentItem[] }> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
    q,
  });
  const res = await fetch(`/api/documents?${params}`);
  if (!res.ok) throw new Error(`获取文档列表失败: ${res.status}`);
  return res.json();
}

export async function fetchDocument(id: number): Promise<DocumentDetail> {
  const res = await fetch(`/api/documents/${id}`);
  if (!res.ok) throw new Error(`获取文档失败: ${res.status}`);
  return res.json();
}

/** 消费 /api/ask 的 SSE 流（POST，需手动解析）。 */
export async function askStream(
  query: string,
  mode: Mode,
  handlers: {
    onCitations: (citations: Citation[]) => void;
    onDelta: (text: string) => void;
    onDone: () => void;
    onError: (message: string) => void;
  },
): Promise<void> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode }),
  });
  if (!res.ok || !res.body) {
    handlers.onError(`请求失败: ${res.status}`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE 事件以空行分隔
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!event) continue;
      try {
        const parsed = JSON.parse(data);
        if (event === "citations") handlers.onCitations(parsed);
        else if (event === "delta") handlers.onDelta(parsed.text);
        else if (event === "done") handlers.onDone();
        else if (event === "error") handlers.onError(parsed.message);
      } catch {
        handlers.onError("响应解析失败");
      }
    }
  }
}
