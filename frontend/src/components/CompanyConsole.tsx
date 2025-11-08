import { useEffect, useMemo, useState } from "react";
import api from "../lib/api";
import type {
  CompanyProfile,
  KnowledgeSection,
  LeadMessage,
  LeadProfile,
  OnboardingAnswerResponse,
  OnboardingSessionResponse,
  StudentGroup
} from "../lib/types";
import { OnboardingWizard } from "./OnboardingWizard";
import { LeadBoard } from "./LeadBoard";

interface CompanyConsoleProps {
  company: CompanyProfile | null;
  onCompanyChange: (company: CompanyProfile | null) => void;
}

export function CompanyConsole({ company, onCompanyChange }: CompanyConsoleProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [nextQuestion, setNextQuestion] = useState<string | null>(null);
  const [insights, setInsights] = useState<string[]>([]);
  const [docRequests, setDocRequests] = useState<string[]>([]);
  const [summary, setSummary] = useState<OnboardingAnswerResponse["summary"]>();
  const [studentGroups, setStudentGroups] = useState<StudentGroup[]>([]);
  const [chatHistory, setChatHistory] = useState<LeadMessage[]>([]);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<"onboarding" | "groups" | "knowledge" | "leads">("onboarding");
  const [knowledgeSections, setKnowledgeSections] = useState<KnowledgeSection[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeMessage, setKnowledgeMessage] = useState<string | null>(null);
  const [leads, setLeads] = useState<LeadProfile[]>([]);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const loadInitialCompany = async () => {
      if (company) return;
      const response = await api.get<CompanyProfile[]>("/company");
      if (response.data.length > 0) {
        onCompanyChange(response.data[0]);
      }
    };
    loadInitialCompany();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startOnboarding = async (payload: { name: string; description?: string; website?: string; companyId?: string }) => {
    setLoading(true);
    try {
      const response = await api.post<OnboardingSessionResponse>("/company/session", {
        name: payload.name,
        description: payload.description,
        website: payload.website,
        company_id: payload.companyId ?? company?.id
      });
      onCompanyChange(response.data.company);
      setSessionId(response.data.session_id);
      setNextQuestion(response.data.next_question);
      setInsights([]);
      setDocRequests([]);
      setSummary(undefined);
      setStudentGroups([]);
      setChatHistory(
        response.data.next_question
          ? [
              {
                message_id: crypto.randomUUID(),
                lead_id: response.data.session_id,
                sender: "agent",
                content: response.data.next_question,
                created_at: new Date().toISOString(),
                metadata: {}
              }
            ]
          : []
      );
      setUploadFeedback(null);
    } finally {
      setLoading(false);
    }
  };

  const submitAnswer = async (answer: string) => {
    if (!sessionId || !company) return;
    setLoading(true);
    const answerMessage: LeadMessage = {
      message_id: crypto.randomUUID(),
      lead_id: sessionId,
      sender: "lead",
      content: answer,
      created_at: new Date().toISOString(),
      metadata: {}
    };
    setChatHistory((prev) => [...prev, answerMessage]);
    try {
      const response = await api.post<OnboardingAnswerResponse>(`/company/session/${sessionId}/answer`, { answer });
      setInsights(response.data.insights ?? []);
      setDocRequests(response.data.document_requests ?? []);
      setNextQuestion(response.data.next_question ?? null);
      if (!response.data.document_requests || response.data.document_requests.length === 0) {
        setUploadFeedback(null);
      }
      if (response.data.summary) {
        setSummary(response.data.summary);
      }
      if (response.data.student_groups) {
        setStudentGroups(response.data.student_groups);
      }
      if (response.data.next_question) {
        setChatHistory((prev) => [
          ...prev,
          {
            message_id: crypto.randomUUID(),
            lead_id: sessionId,
            sender: "agent",
            content: response.data.next_question as string,
            created_at: new Date().toISOString(),
            metadata: {}
          }
        ]);
      }
      if (response.data.status === "completed") {
        const refreshed = await api.get<CompanyProfile>(`/company/${company.id}`);
        onCompanyChange(refreshed.data);
        loadStudentGroups(refreshed.data.id);
        setNextQuestion(null);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleUploadDocuments = async (files: FileList) => {
    if (!company) return;
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("documents", file));
    setUploadFeedback("Uploading documents...");
    try {
      const response = await api.post(`/company/${company.id}/documents`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setUploadFeedback(`Indexed ${response.data.chunks} new chunks across ${response.data.ingested_documents} documents.`);
    } catch (error: any) {
      setUploadFeedback(error?.response?.data?.error ?? "Document upload failed.");
    }
  };

  const loadStudentGroups = async (companyId: string) => {
    const response = await api.get<{ student_groups: StudentGroup[] }>(`/company/${companyId}/groups`);
    setStudentGroups(response.data.student_groups ?? []);
  };

  const loadKnowledgeSections = async () => {
    if (!company) return;
    setKnowledgeLoading(true);
    setKnowledgeMessage(null);
    try {
      const response = await api.get<{ sections: KnowledgeSection[] }>(`/company/${company.id}/knowledge/sections`);
      setKnowledgeSections(response.data.sections ?? []);
    } catch (error: any) {
      setKnowledgeMessage(error?.response?.data?.error ?? "Unable to organize knowledge sections.");
    } finally {
      setKnowledgeLoading(false);
    }
  };

  const saveKnowledgeVisibility = async () => {
    if (!company) return;
    setKnowledgeMessage("Saving visibility preferences...");
    try {
      const internalOnly = knowledgeSections.filter((section) => !section.share_with_clients).map((section) => section.title);
      await api.post(`/company/${company.id}/knowledge/visibility`, { internal_only: internalOnly });
      setKnowledgeMessage("Visibility preferences saved.");
    } catch (error: any) {
      setKnowledgeMessage(error?.response?.data?.error ?? "Failed to save preferences.");
    }
  };

  const loadLeads = async () => {
    if (!company) return;
    setLeadsLoading(true);
    try {
      const response = await api.get<LeadProfile[]>("/leads", {
        params: { company_id: company.id }
      });
      setLeads(response.data);
    } finally {
      setLeadsLoading(false);
    }
  };

  useEffect(() => {
    if (company) {
      loadStudentGroups(company.id);
    }
  }, [company?.id]);

  useEffect(() => {
    if (!company) return;
    if (activePage === "knowledge") {
      loadKnowledgeSections();
    } else if (activePage === "leads") {
      loadLeads();
    }
  }, [activePage, company?.id]);

  const groupedLeads = useMemo(() => {
    const groups: Record<string, LeadProfile[]> = {};
    for (const lead of leads) {
      const key = lead.status || "new";
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(lead);
    }
    return groups;
  }, [leads]);

  const renderActivePage = () => {
    if (!company && activePage !== "onboarding") {
      return (
        <section className="panel">
          <p className="hint">Complete the onboarding chat to unlock this section.</p>
        </section>
      );
    }

    if (activePage === "onboarding") {
      return (
        <OnboardingWizard
          company={company}
          sessionId={sessionId}
          nextQuestion={nextQuestion}
          latestInsights={insights}
          documentRequests={docRequests}
          summary={summary}
          chatHistory={chatHistory}
          uploadFeedback={uploadFeedback}
          loading={loading}
          onStart={startOnboarding}
          onSubmitAnswer={submitAnswer}
          onUploadDocuments={handleUploadDocuments}
        />
      );
    }

    if (activePage === "groups") {
      return (
        <section className="panel">
          <header>
            <h2>Student Groups</h2>
            <span className="badge secondary">{studentGroups.length}</span>
          </header>
          {studentGroups.length === 0 ? (
            <p className="hint">No student groups captured yet. Continue the onboarding chat to add them.</p>
          ) : (
            <ul className="group-list">
              {studentGroups.map((group) => (
                <li key={group.id}>
                  <div className="group-card">
                    {group.profile_image_url && (
                      <img src={group.profile_image_url} alt={group.name} className="group-card__avatar" />
                    )}
                    <h3>{group.name}</h3>
                    {group.summary && <p>{group.summary}</p>}
                    <p className="hint">
                      Focus areas: {group.focus_areas.length > 0 ? group.focus_areas.join(", ") : "n/a"}
                    </p>
                    {group.past_projects.length > 0 && (
                      <p className="hint">Recent work: {group.past_projects.join(", ")}</p>
                    )}
                    {group.availability && <p className="hint">Availability: {group.availability}</p>}
                    {group.contact_email && <p className="hint">Contact: {group.contact_email}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      );
    }

    if (activePage === "knowledge") {
      return (
        <section className="panel">
          <header>
            <h2>Knowledge Base Curation</h2>
            <div className="knowledge-actions">
              <button className="secondary" onClick={loadKnowledgeSections} disabled={knowledgeLoading}>
                {knowledgeLoading ? "Refreshing..." : "Regenerate sections"}
              </button>
              <button className="primary" onClick={saveKnowledgeVisibility} disabled={knowledgeLoading}>
                Save visibility
              </button>
            </div>
          </header>
          {knowledgeMessage && <p className="hint">{knowledgeMessage}</p>}
          {knowledgeSections.length === 0 && !knowledgeLoading ? (
            <p className="hint">Start onboarding or regenerate sections to populate the knowledge base.</p>
          ) : (
            <ul className="knowledge-sections">
              {knowledgeSections.map((section) => (
                <li key={section.title}>
                  <div className="knowledge-card">
                    <div className="knowledge-card__header">
                      <h3>{section.title}</h3>
                      <label>
                        <input
                          type="checkbox"
                          checked={section.share_with_clients}
                          onChange={(event) =>
                            setKnowledgeSections((prev) =>
                              prev.map((item) =>
                                item.title === section.title
                                  ? { ...item, share_with_clients: event.target.checked }
                                  : item
                              )
                            )
                          }
                        />
                        Share with clients
                      </label>
                    </div>
                    <p>{section.summary}</p>
                    <ul>
                      {section.key_points.map((point, index) => (
                        <li key={index}>{point}</li>
                      ))}
                    </ul>
                    <p className="hint">Recommended audience: {section.recommended_audience}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      );
    }

    return (
        <LeadBoard
          leadsByStatus={groupedLeads}
          loading={leadsLoading}
          onRefresh={loadLeads}
        />
    );
  };

  const pages = [
    { id: "onboarding", label: "Onboarding chat" },
    { id: "groups", label: "Student groups" },
    { id: "knowledge", label: "Knowledge base" },
    { id: "leads", label: "Leads board" }
  ] as const;

  return (
    <section className="company-console">
      <nav className="page-tabs">
        {pages.map((page) => (
          <button
            key={page.id}
            type="button"
            className={activePage === page.id ? "active" : ""}
            onClick={() => setActivePage(page.id)}
            disabled={!company && page.id !== "onboarding"}
          >
            {page.label}
          </button>
        ))}
      </nav>
      <div className="page-content">{renderActivePage()}</div>
    </section>
  );
}

