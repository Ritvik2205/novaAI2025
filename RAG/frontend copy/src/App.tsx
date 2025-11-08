import { useEffect, useMemo, useRef, useState } from "react";

type NamespaceSummary = {
  namespace: string;
  pages_indexed: number | null;
  chunks_indexed: number | null;
};

type QueryRequest = {
  question: string;
  namespace: string | null;
};

type Citation = {
  label: string;
  url: string;
  snippet: string;
};

type QueryResponse = {
  answer: string;
  citations: Citation[];
};

type Message = {
  id: string;
  sender: "user" | "assistant";
  text: string;
  citations?: Citation[];
};

const API_BASE = ""; // same origin

async function fetchNamespaces(): Promise<NamespaceSummary[]> {
  const res = await fetch(`/rag/namespaces`);
  if (!res.ok) {
    throw new Error("Failed to load namespaces");
  }
  return res.json();
}

async function postQuery(payload: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`/rag/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? "Query failed");
  }
  return res.json();
}

type ParsedAnswer = {
  paragraphs: string[];
  bullets: string[];
  referencesLine?: string;
};

function parseAnswer(answer: string): ParsedAnswer {
  const [rawBody, rawReferences] = answer.split(/References:/i);
  const bodyLines = rawBody
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const bullets: string[] = [];
  const paragraphs: string[] = [];

  bodyLines.forEach((line) => {
    if (/^[-•]/.test(line)) {
      bullets.push(line.replace(/^[-•]\s*/, ""));
    } else {
      paragraphs.push(line);
    }
  });

  return {
    paragraphs,
    bullets,
    referencesLine: rawReferences?.trim()
      ? `References: ${rawReferences.trim()}`
      : undefined,
  };
}

function MessageBubble({ message }: { message: Message }) {
  const parsed = parseAnswer(message.text);
  const isAssistant = message.sender === "assistant";

  const hasCitations = Boolean(message.citations && message.citations.length > 0);

  return (
    <div className={`bubble ${isAssistant ? "assistant" : "user"}`}>
      <div className="bubble__meta">
        <span className="bubble__role">{isAssistant ? "Assistant" : "You"}</span>
        {isAssistant && hasCitations && <span className="bubble__badge">cited</span>}
      </div>
      <div className="bubble__content">
        {parsed.paragraphs.map((paragraph, idx) => (
          <p key={idx}>{paragraph}</p>
        ))}
        {parsed.bullets.length > 0 && (
          <ul className="bubble__bullets">
            {parsed.bullets.map((bullet, idx) => (
              <li key={idx}>{bullet}</li>
            ))}
          </ul>
        )}
      </div>
      {isAssistant && hasCitations && (
        <div className="bubble__citations">
          <h4>Sources</h4>
          <ul>
            {message.citations.map((citation) => (
              <li key={citation.label}>
                <a href={citation.url} target="_blank" rel="noreferrer">
                  {citation.label}
                </a>
                <span>{citation.snippet}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {isAssistant && hasCitations && parsed.referencesLine && (
        <div className="bubble__references">{parsed.referencesLine}</div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="typing">
      <div className="typing__bubble">
        <span />
        <span />
        <span />
      </div>
      <p>Assistant is thinking…</p>
    </div>
  );
}

export default function App() {
  const [namespaces, setNamespaces] = useState<NamespaceSummary[]>([]);
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingNamespaces, setLoadingNamespaces] = useState(false);
  const [initialLoadError, setInitialLoadError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    async function loadNamespaces() {
      setLoadingNamespaces(true);
      try {
        const data = await fetchNamespaces();
        setNamespaces(data);
        setSelectedNamespace((current) => current ?? data[0]?.namespace ?? null);
      } catch (error) {
        setInitialLoadError((error as Error).message);
      } finally {
        setLoadingNamespaces(false);
      }
    }

    loadNamespaces();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const namespaceLabel = useMemo(() => {
    if (!selectedNamespace) return "No knowledge base";
    return namespaces.find((ns) => ns.namespace === selectedNamespace)?.namespace ?? selectedNamespace;
  }, [namespaces, selectedNamespace]);

  async function handleSend() {
    if (!question.trim()) return;
    if (!selectedNamespace) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: "assistant",
          text: "Please ingest a site before asking questions.",
        },
      ]);
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      sender: "user",
      text: question.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setIsSending(true);

    try {
      const response = await postQuery({
        question: userMessage.text,
        namespace: selectedNamespace,
      });

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: "assistant",
          text: response.answer,
          citations: response.citations,
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: "assistant",
          text: (error as Error).message,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="layout">
      <div className="backdrop" />
      <div className="panel">
        <header className="header">
          <div className="branding">
            <span className="branding__logo">V</span>
            <div>
              <h1>Venture Support Copilot</h1>
              <p>Concise, source-backed answers for your websites.</p>
            </div>
          </div>
          <div className="selectors">
            <label htmlFor="namespace">Knowledge base</label>
            <div className="select-wrapper">
              <select
                id="namespace"
                value={selectedNamespace ?? ""}
                onChange={(e) => setSelectedNamespace(e.target.value || null)}
                disabled={loadingNamespaces}
              >
                {namespaces.length === 0 ? (
                  <option value="">No ingested sites</option>
                ) : (
                  namespaces.map((option) => (
                    <option key={option.namespace} value={option.namespace}>
                      {option.namespace}
                    </option>
                  ))
                )}
              </select>
            </div>
            <span className="namespace-pill">{namespaceLabel}</span>
          </div>
        </header>

        <main className="chat">
          {initialLoadError && (
            <div className="callout callout--error">
              <strong>Failed to load namespaces.</strong>
              <span>{initialLoadError}</span>
            </div>
          )}

          <div className="messages">
            {messages.length === 0 && (
              <div className="empty">
                <h2>Ready when you are</h2>
                <p>
                  Choose a knowledge base above, then ask a question like “What is the refund policy?” –
                  answers will stay crisp and cited.
                </p>
              </div>
            )}

            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {isSending && <TypingIndicator />}
            <div ref={chatEndRef} />
          </div>
        </main>

        <footer className="composer">
          <div className="composer__field">
            <textarea
              placeholder={selectedNamespace ? "Ask a question..." : "Ingest a site before querying"}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSending || !selectedNamespace}
              rows={2}
            />
          </div>
          <button onClick={handleSend} disabled={isSending || !question.trim() || !selectedNamespace}>
            {isSending ? "Thinking..." : "Send"}
          </button>
        </footer>
      </div>
    </div>
  );
}
