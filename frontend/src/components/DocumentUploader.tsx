import { useCallback, useEffect, useState } from "react";
import api from "../lib/api";
import type { CompanyDocument } from "../lib/types";

interface DocumentUploaderProps {
  companyId: string;
}

export function DocumentUploader({ companyId }: DocumentUploaderProps) {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [urls, setUrls] = useState("");
  const [documents, setDocuments] = useState<CompanyDocument[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoadingList(true);
    try {
      const response = await api.get<{ documents: CompanyDocument[] }>(`/company/${companyId}/documents`);
      setDocuments(response.data.documents ?? []);
    } catch (error) {
      console.error("Failed to load documents", error);
    } finally {
      setLoadingList(false);
    }
  }, [companyId]);

  useEffect(() => {
    if (!companyId) return;
    fetchDocuments();
  }, [companyId, fetchDocuments]);

  const handleFileUpload = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = (event.currentTarget.elements.namedItem("documents") as HTMLInputElement) ?? null;
    if (!input || !input.files || input.files.length === 0) return;

    const formData = new FormData();
    Array.from(input.files).forEach((file) => formData.append("documents", file));

    try {
      setUploading(true);
      const response = await api.post(`/company/${companyId}/documents`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      setMessage(`Indexed ${response.data.chunks} knowledge chunks from ${response.data.ingested_documents} files.`);
      input.value = "";
      fetchDocuments();
    } catch (error: any) {
      setMessage(error?.response?.data?.error ?? "Failed to upload files.");
    } finally {
      setUploading(false);
    }
  };

  const handleUrlIngest = async (event: React.FormEvent) => {
    event.preventDefault();
    const list = urls
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (list.length === 0) return;
    try {
      setUploading(true);
      const response = await api.post(`/company/${companyId}/urls`, { urls: list });
      setMessage(`Crawled ${response.data.pages} pages and created ${response.data.chunks} vector entries.`);
      setUrls("");
      fetchDocuments();
    } catch (error: any) {
      setMessage(error?.response?.data?.error ?? "Failed to crawl URLs.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="panel">
      <header>
        <h2>Knowledge Builder</h2>
        <span className="badge secondary">RAG ingestion</span>
      </header>

      <form className="form-grid" onSubmit={handleFileUpload}>
        <label className="full-width file-input">
          Upload documents (PDF, DOCX, TXT)
          <input type="file" name="documents" multiple accept=".pdf,.doc,.docx,.txt,.md" />
        </label>
        <button type="submit" className="secondary" disabled={uploading}>
          {uploading ? "Processing..." : "Index files"}
        </button>
      </form>

      <form className="form-grid" onSubmit={handleUrlIngest}>
        <label className="full-width">
          Crawl company URLs (one per line)
          <textarea value={urls} onChange={(event) => setUrls(event.target.value)} placeholder="https://..."></textarea>
        </label>
        <button type="submit" className="secondary" disabled={uploading}>
          {uploading ? "Scanning..." : "Scan website"}
        </button>
      </form>

      <div className="document-list">
        <h3>Indexed knowledge</h3>
        {loadingList ? (
          <p className="hint">Loading documents...</p>
        ) : documents.length === 0 ? (
          <p className="hint">No documents ingested yet.</p>
        ) : (
          <ul>
            {documents.map((doc) => (
              <li key={doc.path}>
                <span>{doc.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {message && <p className="hint">{message}</p>}
    </section>
  );
}

