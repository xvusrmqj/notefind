import { useState } from "react";
import AskPage from "./AskPage";
import SearchPage from "./SearchPage";
import SyncPage from "./SyncPage";
import DocsPage from "./DocsPage";

type Tab = "ask" | "search" | "sync" | "docs";

const TABS: { key: Tab; label: string }[] = [
  { key: "ask", label: "问答" },
  { key: "search", label: "搜索" },
  { key: "sync", label: "同步" },
  { key: "docs", label: "文档" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  return (
    <div className="app">
      <header className="header">
        <span className="logo">notefind</span>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? "tab active" : "tab"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="main">
        {tab === "ask" && <AskPage />}
        {tab === "search" && <SearchPage />}
        {tab === "sync" && <SyncPage />}
        {tab === "docs" && <DocsPage />}
      </main>
    </div>
  );
}
