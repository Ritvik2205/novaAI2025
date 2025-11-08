import { useState } from "react";
import type { CompanyProfile } from "./lib/types";
import { CompanyConsole } from "./components/CompanyConsole";
import { ClientPortal } from "./components/ClientPortal";

function App() {
  const [mode, setMode] = useState<"company" | "client">("company");
  const [company, setCompany] = useState<CompanyProfile | null>(null);

  return (
    <div className={`app ${mode === "client" ? "app-client" : ""}`}>
      <div className="mode-switch">
        <button className={mode === "company" ? "primary" : "secondary"} onClick={() => setMode("company")}>
          Company console
        </button>
        <button className={mode === "client" ? "primary" : "secondary"} onClick={() => setMode("client")}>
          Client portal
        </button>
      </div>

      {mode === "company" && (
        <header className="hero">
          <h1>SuperNOVA CRM</h1>
          <p>
            Multi-agent system that learns your business, indexes institutional knowledge, qualifies inbound leads, and
            schedules work automatically.
          </p>
        </header>
      )}

      <main className={mode === "company" ? "grid" : "client-layout"}>
        {mode === "company" ? (
          <CompanyConsole company={company} onCompanyChange={setCompany} />
        ) : (
          <ClientPortal />
        )}
      </main>
    </div>
  );
}

export default App;

