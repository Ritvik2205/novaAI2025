import type { LeadProfile } from "../lib/types";

const STATUS_ORDER: Array<{ key: string; label: string }> = [
  { key: "new", label: "New Leads" },
  { key: "engaged", label: "Engaged" },
  { key: "qualified", label: "Qualified" },
  { key: "quoted", label: "Quoted" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Archived" }
];

interface LeadBoardProps {
  leadsByStatus: Record<string, LeadProfile[]>;
  loading: boolean;
  onRefresh: () => Promise<void> | void;
}

export function LeadBoard({ leadsByStatus, loading, onRefresh }: LeadBoardProps) {
  return (
    <section className="panel lead-board">
      <header>
        <h2>Lead Pipeline</h2>
        <button className="secondary" onClick={onRefresh} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>
      <div className="lead-board__columns">
        {STATUS_ORDER.map(({ key, label }) => {
          const leads = leadsByStatus[key] ?? [];
          return (
            <div key={key} className="lead-column">
              <h3>
                {label} <span className="badge secondary">{leads.length}</span>
              </h3>
              {leads.length === 0 ? (
                <p className="hint">No leads in this stage.</p>
              ) : (
                <ul>
                  {leads.map((lead) => (
                    <li key={lead.id}>
                      <strong>{lead.name || "Unnamed lead"}</strong>
                      {lead.email && <p className="hint">{lead.email}</p>}
                      {lead.preferences && Object.keys(lead.preferences).length > 0 && (
                        <p className="hint">
                          {Object.entries(lead.preferences)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(" · ")}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

