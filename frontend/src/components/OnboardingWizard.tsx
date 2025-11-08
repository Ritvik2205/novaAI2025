import { useState } from "react";
import type { CompanyProfile, OnboardingAnswerResponse, LeadMessage } from "../lib/types";

interface OnboardingWizardProps {
  company: CompanyProfile | null;
  sessionId: string | null;
  nextQuestion: string | null;
  latestInsights: string[];
  documentRequests: string[];
  summary: OnboardingAnswerResponse["summary"] | undefined;
  chatHistory: LeadMessage[];
  uploadFeedback: string | null;
  loading: boolean;
  onStart: (payload: { name: string; description?: string; website?: string; companyId?: string }) => Promise<void>;
  onSubmitAnswer: (answer: string) => Promise<void>;
  onUploadDocuments: (files: FileList) => Promise<void>;
}

export function OnboardingWizard({
  company,
  sessionId,
  nextQuestion,
  latestInsights,
  documentRequests,
  summary,
  chatHistory,
  uploadFeedback,
  loading,
  onStart,
  onSubmitAnswer,
  onUploadDocuments
}: OnboardingWizardProps) {
  const [form, setForm] = useState({ name: "", website: "", description: "" });
  const [answer, setAnswer] = useState("");

  const handleStart = async (event: React.FormEvent) => {
    event.preventDefault();
    await onStart(form);
  };

  const handleResume = async () => {
    if (!company) return;
    await onStart({
      name: company.name,
      website: company.website ?? undefined,
      description: company.description ?? undefined,
      companyId: company.id
    });
  };

  const handleAnswer = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!answer.trim()) return;
    await onSubmitAnswer(answer);
    setAnswer("");
  };

  return (
    <section className="panel">
      <header>
        <h2>Company Onboarding</h2>
        {company ? <span className="badge">Active</span> : <span className="badge">Start</span>}
      </header>

      {!company && (
        <form className="form-grid" onSubmit={handleStart}>
          <label>
            Company Name
            <input
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Acme Contractors"
            />
          </label>
          <label>
            Website
            <input
              value={form.website}
              onChange={(event) => setForm({ ...form, website: event.target.value })}
              placeholder="https://example.com"
            />
          </label>
          <label className="full-width">
            Elevator Pitch
            <textarea
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder="Share services, geography, differentiators..."
            />
          </label>
          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Starting..." : "Launch Onboarding"}
          </button>
        </form>
      )}

      {company && !sessionId && (
        <div className="qa-card">
          <p>
            ScottyLabs is already in the system. Kick off a new discovery round to refresh student group data or upload
            new playbooks.
          </p>
          <button type="button" className="primary" onClick={handleResume} disabled={loading}>
            {loading ? "Preparing..." : "Start discovery session"}
          </button>
        </div>
      )}

      {company && sessionId && nextQuestion && (
        <div className="chat-panel">
          <div className="chat-transcript">
            {chatHistory.length === 0 && nextQuestion && (
              <div className="chat-row agent">
                <p>{nextQuestion}</p>
              </div>
            )}
            {chatHistory.map((entry) => (
              <div key={entry.message_id} className={`chat-row ${entry.sender === "lead" ? "user" : "agent"}`}>
                <p>{entry.content}</p>
              </div>
            ))}
          </div>

          <form className="chat-input" onSubmit={handleAnswer}>
            <textarea
              required
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder="Share details, metrics, and attach references if relevant."
              rows={3}
            />
            <button type="submit" className="primary" disabled={loading}>
              {loading ? "Sending..." : "Submit answer"}
            </button>
          </form>

          {documentRequests.length > 0 && (
            <div className="document-requests">
              <h4>Requested documents</h4>
              <ul>
                {documentRequests.map((request, index) => (
                  <li key={index}>
                    <span>{request}</span>
                    <input
                      type="file"
                      multiple
                      onChange={async (event) => {
                        if (event.target.files) {
                          await onUploadDocuments(event.target.files);
                          event.target.value = "";
                        }
                      }}
                    />
                  </li>
                ))}
              </ul>
              {uploadFeedback && <p className="hint">{uploadFeedback}</p>}
            </div>
          )}
        </div>
      )}

      {latestInsights.length > 0 && (
        <div className="insights">
          <h3>Fresh Insights</h3>
          <ul>
            {latestInsights.map((insight, index) => (
              <li key={index}>{insight}</li>
            ))}
          </ul>
        </div>
      )}

      {documentRequests.length > 0 && (
        <div className="insights">
          <h3>Document Requests</h3>
          <ul>
            {documentRequests.map((doc, index) => (
              <li key={index}>{doc}</li>
            ))}
          </ul>
        </div>
      )}

      {summary && (
        <div className="summary">
          <h3>Operating Profile</h3>
          <p>{summary.profile}</p>
          <h4>Recommended Actions</h4>
          <ul>
            {summary.recommendations.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
          {summary.key_contacts.length > 0 && (
            <>
              <h4>Key Contacts</h4>
              <ul>
                {summary.key_contacts.map((contact, index) => (
                  <li key={index}>
                    {contact.name} — {contact.role} {contact.email && `(${contact.email})`}
                  </li>
                ))}
              </ul>
            </>
          )}
          {summary.student_groups_overview && summary.student_groups_overview.length > 0 && (
            <>
              <h4>Student Groups at a Glance</h4>
              <ul>
                {summary.student_groups_overview.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {summary.data_gaps.length > 0 && (
            <>
              <h4>Still Needed</h4>
              <ul>
                {summary.data_gaps.map((gap, index) => (
                  <li key={index}>{gap}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}

