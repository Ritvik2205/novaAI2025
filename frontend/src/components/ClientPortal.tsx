import { FormEvent, useCallback, useMemo, useState } from "react";
import dayjs from "dayjs";
import api from "../lib/api";
import type {
  LeadDetailResponse,
  LeadMessage,
  LeadProfile,
  MonitorSummary,
  Quote,
  Meeting,
  LeadRecommendation
} from "../lib/types";

export function ClientPortal() {
  const [lead, setLead] = useState<LeadProfile | null>(null);
  const [messages, setMessages] = useState<LeadMessage[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [monitorSummary, setMonitorSummary] = useState<MonitorSummary | null>(null);
  const [scheduledMeeting, setScheduledMeeting] = useState<Meeting | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientCode, setClientCode] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<LeadRecommendation[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [handoffStatus, setHandoffStatus] = useState<"idle" | "sent" | "declined">("idle");
  const [handoffMessage, setHandoffMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    projectSummary: ""
  });
  const [draft, setDraft] = useState("");

  const loadConversation = useCallback(async (leadId: string) => {
    try {
      const response = await api.get<LeadDetailResponse>(`/leads/${leadId}`);
      const detail = response.data;
      setLead(detail.lead);
      setMessages(detail.messages);
      setQuotes(detail.quotes);
      setMonitorSummary(detail.monitor_summary ?? null);
    } catch (err) {
      console.error("Failed to load conversation", err);
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string, initial: boolean) => {
      if (!content.trim()) return;
      setPending(true);
      setError(null);
      try {
        const payload: Record<string, any> = {
          message: content
        };
        if (lead) {
          payload.lead_id = lead.id;
        } else {
          payload.name = form.name;
          payload.email = form.email;
          payload.phone = form.phone;
        }
        const response = await api.post(`/leads/message`, payload);
        const data = response.data as {
          lead: LeadProfile;
          reply?: string;
          monitor_summary?: MonitorSummary;
          quote?: Quote | null;
          meeting?: Meeting | null;
          recommendations?: LeadRecommendation[];
          client_code?: string;
        };
        setLead(data.lead);
        setMonitorSummary(data.monitor_summary ?? null);
        if (data.client_code) {
          setClientCode(data.client_code);
        }
        setRecommendations(data.recommendations ?? []);
        setSelectedGroupId(null);
        setHandoffStatus("idle");
        setHandoffMessage(null);
        if (data.meeting) {
          setScheduledMeeting(data.meeting);
        }
        if (data.quote) {
          setQuotes((prev) => [...prev, data.quote!]);
        }
        await loadConversation(data.lead.id);
        if (initial) {
          setForm((prev) => ({ ...prev, projectSummary: "" }));
        } else {
          setDraft("");
        }
      } catch (err: any) {
        const message = err?.response?.data?.error ?? "Something went wrong. Please try again.";
        setError(message);
      } finally {
        setPending(false);
      }
    },
    [form, lead, loadConversation]
  );

  const handleStart = async (event: FormEvent) => {
    event.preventDefault();
    await sendMessage(form.projectSummary, true);
  };

  const handleSend = async (event: FormEvent) => {
    event.preventDefault();
    await sendMessage(draft, false);
  };

  const handleHandoff = async (decision: "send" | "decline") => {
    if (!lead) return;
    if (decision === "send" && !selectedGroupId) {
      setError("Select a student group first.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await api.post(`/leads/${lead.id}/handoff`, {
        decision,
        group_id: decision === "send" ? selectedGroupId : undefined
      });
      if (decision === "send") {
        setHandoffStatus("sent");
        const selected = recommendations.find((item) => item.id === selectedGroupId);
        const message = selected
          ? `Thanks! We've shared your project details with ${selected.name}. They'll reach out via email soon.`
          : "Thanks! We've shared your project details with the selected student group.";
        setHandoffMessage(message);
      } else {
        setHandoffStatus("declined");
        const message = "Understood! We won't share your information. Feel free to continue the conversation anytime.";
        setHandoffMessage(message);
      }
      setRecommendations([]);
      setSelectedGroupId(null);
      await loadConversation(lead.id);
    } catch (err: any) {
      const message = err?.response?.data?.error ?? "Unable to update preference. Please try again.";
      setError(message);
    } finally {
      setPending(false);
    }
  };

  const selectedGroup = useMemo(
    () => recommendations.find((item) => item.id === selectedGroupId),
    [recommendations, selectedGroupId]
  );

  return (
    <div className="client-portal-wrapper">
      <div className="client-portal-background" />
      <section className="client-portal-modal">
        <header>
          <h2>ScottyLabs Concierge</h2>
          <p className="hint">
            Tell us what you need and our AI concierge will match you with the right student builders.
          </p>
        </header>

        {!lead ? (
          <form className="form-grid" onSubmit={handleStart}>
            <label>
              Your name
              <input
                required
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              />
            </label>
            <label>
              Email
              <input
                required
                type="email"
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
              />
            </label>
            <label>
              Phone
              <input
                value={form.phone}
                onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
              />
            </label>
            <label className="full-width">
              Describe what you need
              <textarea
                required
                value={form.projectSummary}
                onChange={(event) => setForm((prev) => ({ ...prev, projectSummary: event.target.value }))}
                placeholder="Tell us about your project, timelines, budget, and any constraints."
              />
            </label>
            <button type="submit" className="primary" disabled={pending}>
              {pending ? "Connecting..." : "Start chat"}
            </button>
            {error && <p className="hint error">{error}</p>}
          </form>
        ) : (
          <>
            {clientCode && (
              <div className="client-code-badge">
                Project code <strong>{clientCode}</strong>
              </div>
            )}
            <div className="chat-window">
              {messages.map((message) => (
                <div
                  key={message.message_id}
                  className={`chat-bubble ${message.sender === "lead" ? "incoming" : "outgoing"}`}
                >
                  <div className="chat-meta">
                    <strong>{message.sender === "lead" ? form.name || "You" : "Agent"}</strong>
                    <span>{dayjs(message.created_at).format("MMM D, HH:mm")}</span>
                  </div>
                  <p>{message.content}</p>
                </div>
              ))}
            </div>

            {recommendations.length > 0 && handoffStatus === "idle" && (
              <div className="recommendations-panel">
                <h3>Recommended student groups</h3>
                <p className="hint">Choose the team you’d like to collaborate with.</p>
                <div className="recommendation-grid">
                  {recommendations.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      className={`recommendation-card ${selectedGroupId === group.id ? "selected" : ""}`}
                      onClick={() => setSelectedGroupId(group.id)}
                    >
                      {group.profile_image_url && (
                        <img src={group.profile_image_url} alt={group.name} />
                      )}
                      <h4>{group.name}</h4>
                      {group.summary && <p>{group.summary}</p>}
                      <span className="tag">
                        Focus: {group.focus_areas.length > 0 ? group.focus_areas.join(", ") : "Generalist"}
                      </span>
                      {group.hire_rate && <span className="tag">Rate: {group.hire_rate}</span>}
                    </button>
                  ))}
                </div>
                {selectedGroup && (
                  <div className="handoff-actions">
                    <button
                      type="button"
                      className="primary"
                      onClick={() => handleHandoff("send")}
                      disabled={pending}
                    >
                      Send my information
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => handleHandoff("decline")}
                      disabled={pending}
                    >
                      Don&apos;t send my info
                    </button>
                  </div>
                )}
              </div>
            )}

            {handoffMessage && <p className="hint">{handoffMessage}</p>}

            <form className="chat-input" onSubmit={handleSend}>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Share more details or ask follow-up questions…"
                rows={3}
              />
              <button className="primary" disabled={pending}>
                {pending ? "Sending..." : "Send"}
              </button>
            </form>

            {monitorSummary && (
              <div className="summary">
                <h3>What we captured</h3>
                {monitorSummary.summary && <p>{monitorSummary.summary}</p>}
                {monitorSummary.action_items && monitorSummary.action_items.length > 0 && (
                  <>
                    <h4>Action items</h4>
                    <ul>
                      {monitorSummary.action_items.map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  </>
                )}
                {lead?.metadata?.assigned_contractor && (
                  <>
                    <h4>Your specialist</h4>
                    <p>
                      {lead.metadata.assigned_contractor}
                      {lead.metadata.assignment_reason && ` — ${lead.metadata.assignment_reason}`}
                    </p>
                  </>
                )}
              </div>
            )}

            {scheduledMeeting && (
              <div className="summary">
                <h3>Upcoming session</h3>
                <p>
                  {scheduledMeeting.summary} on{" "}
                  {dayjs(scheduledMeeting.start_time).format("MMM D, YYYY @ HH:mm")} ({scheduledMeeting.host} host)
                </p>
                {scheduledMeeting.conferencing_link && (
                  <a href={scheduledMeeting.conferencing_link} className="hint" target="_blank" rel="noreferrer">
                    Join link
                  </a>
                )}
              </div>
            )}

            {quotes.length > 0 && (
              <div className="summary">
                <h3>Quote drafts</h3>
                <ul>
                  {quotes.map((quote) => (
                    <li key={quote.id}>
                      <strong>
                        {quote.currency} {quote.price.toLocaleString()}
                      </strong>
                      <p>{quote.scope_summary}</p>
                      <small>Estimated timeline: {quote.delivery_timeline}</small>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {error && <p className="hint error">{error}</p>}
          </>
        )}
      </section>
    </div>
  );
}

