import { useState } from "react";
import api from "../lib/api";
import type { KnowledgeResult } from "../lib/types";

interface KnowledgeConsoleProps {
  companyId: string;
}

export function KnowledgeConsole({ companyId }: KnowledgeConsoleProps) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<KnowledgeResult | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    try {
      setLoading(true);
      const response = await api.post(`/chat/company/${companyId}`, { question });
      setResult(response.data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="panel">
      <header>
        <h2>Knowledge Copilot</h2>
      </header>
      <form className="form-grid" onSubmit={ask}>
        <label className="full-width">
          Ask a question
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How do we price rush residential remodels?"
          />
        </label>
        <button className="primary" disabled={loading}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>
      {result && (
        <div className="summary">
          <h3>Answer</h3>
          <p>{result.answer}</p>
          <h4>Context</h4>
          <ul>
            {result.context.map((chunk, index) => (
              <li key={index}>
                {chunk.text}
                {chunk.url && (
                  <>
                    {" "}
                    <a href={chunk.url} target="_blank" rel="noreferrer">
                      source
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

