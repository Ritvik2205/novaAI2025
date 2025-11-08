import { useCallback, useEffect, useState } from "react";
import dayjs from "dayjs";
import api from "../lib/api";
import type {
  LeadDetailResponse,
  LeadMessage,
  LeadProfile,
  MonitorSummary,
  Quote
} from "../lib/types";

interface LeadInboxProps {
  companyId: string;
}

export function LeadInbox({ companyId }: LeadInboxProps) {
  const [leads, setLeads] = useState<LeadProfile[]>([]);
  const [selectedLead, setSelectedLead] = useState<LeadProfile | null>(null);
  const [messages, setMessages] = useState<LeadMessage[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [monitorSummary, setMonitorSummary] = useState<MonitorSummary | null>(null);
  const [loadingLeads, setLoadingLeads] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);

  const loadLeads = useCallback(async () => {
    setLoadingLeads(true);
    try {
      const response = await api.get<LeadProfile[]>(`/leads`, {
        params: { company_id: companyId }
      });
      setLeads(response.data);
    } catch (error) {
      console.error("Failed to fetch leads", error);
    } finally {
      setLoadingLeads(false);
    }
  }, [companyId]);

  const loadLeadDetail = useCallback(
    async (leadId: string) => {
      setLoadingConversation(true);
      try {
        const response = await api.get<LeadDetailResponse>(`/leads/${leadId}`);
        const detail = response.data;
        setSelectedLead(detail.lead);
        setMessages(detail.messages);
        setQuotes(detail.quotes);
        setMonitorSummary(detail.monitor_summary ?? null);
      } catch (error) {
        console.error("Failed to load lead detail", error);
      } finally {
        setLoadingConversation(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!companyId) return;
    loadLeads();
  }, [companyId, loadLeads]);

  return (
    <section className="panel lead-inbox">
      <header>
        <h2>Leads & Conversations</h2>
        <button className="secondary" onClick={loadLeads} disabled={loadingLeads}>
          {loadingLeads ? "Refreshing..." : "Refresh"}
        </button>
      </header>
      <div className="lead-inbox__body">
        <aside className="lead-inbox__list">
          {leads.length === 0 ? (
            <p className="hint">No leads yet. Incoming enquiries appear here in real time.</p>
          ) : (
            <ul>
              {leads.map((lead) => (
                <li
                  key={lead.id}
                  className={lead.id === selectedLead?.id ? "active" : ""}
                  onClick={() => loadLeadDetail(lead.id)}
                >
                  <strong>{lead.name || "Unnamed lead"}</strong>
                  <span className="status">{lead.status}</span>
                  {lead.action_items?.length ? (
                    <small>{lead.action_items[lead.action_items.length - 1]}</small>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </aside>

        <article className="lead-inbox__conversation">
          {!selectedLead ? (
            <p className="hint">Select a lead to review the conversation and captured actions.</p>
          ) : loadingConversation ? (
            <p className="hint">Loading conversation…</p>
          ) : (
            <>
              <div className="conversation-header">
                <div>
                  <h3>{selectedLead.name || "Lead"}</h3>
                  <p className="hint">{selectedLead.email || selectedLead.phone || "No contact info yet"}</p>
                  {selectedLead.metadata?.assigned_contractor && (
                    <p className="hint">
                      Assigned contractor: {selectedLead.metadata.assigned_contractor}
                      {selectedLead.metadata.assignment_reason && (
                        <> — {selectedLead.metadata.assignment_reason}</>
                      )}
                    </p>
                  )}
                </div>
                <span className="badge">{selectedLead.status}</span>
              </div>

              <div className="chat-window">
                {messages.map((message) => (
                  <div
                    key={message.message_id}
                    className={`chat-bubble ${message.sender === "lead" ? "incoming" : "outgoing"}`}
                  >
                    <div className="chat-meta">
                      <strong>{message.sender === "lead" ? selectedLead.name || "Lead" : message.sender}</strong>
                      <span>{dayjs(message.created_at).format("MMM D, HH:mm")}</span>
                    </div>
                    <p>{message.content}</p>
                  </div>
                ))}
              </div>

              {monitorSummary && (
                <div className="summary">
                  <h4>Latest agent summary</h4>
                  {monitorSummary.summary && <p>{monitorSummary.summary}</p>}
                  {monitorSummary.action_items && monitorSummary.action_items.length > 0 && (
                    <>
                      <h5>Action items</h5>
                      <ul>
                        {monitorSummary.action_items.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}

              {quotes.length > 0 && (
                <div className="summary">
                  <h4>Quotes shared</h4>
                  <ul>
                    {quotes.map((quote) => (
                      <li key={quote.id}>
                        <strong>
                          {quote.currency} {quote.price.toLocaleString()}
                        </strong>
                        <p>{quote.scope_summary}</p>
                        <small>Timeline: {quote.delivery_timeline}</small>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </article>
      </div>
    </section>
  );
}

