export interface CompanyProfile {
  id: string;
  name: string;
  description?: string | null;
  website?: string | null;
  tags: string[];
  metadata: Record<string, string>;
  documents: string[];
  knowledge_base_ids: string[];
}

export interface OnboardingSessionResponse {
  company: CompanyProfile;
  session_id: string;
  next_question: string;
}

export interface OnboardingAnswerResponse {
  status: "active" | "completed";
  insights?: string[];
  document_requests?: string[];
  next_question?: string | null;
  summary?: {
    profile: string;
    recommendations: string[];
    key_contacts: Array<{ name: string; role?: string; email?: string }>;
    student_groups_overview: string[];
    data_gaps: string[];
  };
  student_groups?: StudentGroup[];
}

export interface LeadProfile {
  id: string;
  company_id: string;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  status: string;
  preferences: Record<string, string>;
  notes: string[];
  metadata: Record<string, string>;
  action_items: string[];
  quoted_price?: number | null;
  proposed_delivery_date?: string | null;
  meetings: string[];
}

export interface LeadMessage {
  message_id: string;
  lead_id: string;
  sender: "lead" | "agent" | "human";
  content: string;
  created_at: string;
  metadata: Record<string, string>;
}

export interface MonitorSummary {
  summary?: string;
  action_items?: string[];
  lead_updates?: {
    status?: string;
    preferences?: Record<string, string>;
    notes?: string[];
  };
  schedule?: {
    should_schedule?: boolean;
    preferred_start?: string | null;
    duration_minutes?: number;
    assignees?: string[];
    fallback_to_agent?: boolean;
  };
  quote?: {
    price?: number;
    currency?: string;
    scope_summary?: string;
    delivery_timeline?: string;
    assumptions?: string[];
  } | null;
}

export interface LeadDetailResponse {
  lead: LeadProfile;
  messages: LeadMessage[];
  quotes: Quote[];
  monitor_summary?: MonitorSummary | null;
}

export interface Quote {
  id: string;
  price: number;
  currency: string;
  scope_summary: string;
  delivery_timeline: string;
  assumptions: string[];
}

export interface Meeting {
  id: string;
  lead_id: string;
  company_id: string;
  summary: string;
  start_time: string;
  end_time: string;
  attendees: string[];
  host: "human" | "agent";
  location?: string | null;
  conferencing_link?: string | null;
}

export interface KnowledgeResult {
  answer: string;
  context: Array<{
    text: string;
    source?: string;
    url?: string;
  }>;
}

export interface CompanyDocument {
  path: string;
  name: string;
}

export interface StudentGroup {
  id: string;
  company_id: string;
  name: string;
  summary?: string | null;
  focus_areas: string[];
  past_projects: string[];
  preferred_tools: string[];
  contact_email?: string | null;
  availability?: string | null;
  profile_image_url?: string | null;
  metadata: Record<string, string>;
}

export interface KnowledgeSection {
  title: string;
  summary: string;
  key_points: string[];
  recommended_audience: "client" | "internal" | "both";
  share_with_clients: boolean;
}

export interface LeadRecommendation {
  id: string;
  name: string;
  summary?: string | null;
  focus_areas: string[];
  profile_image_url?: string | null;
  hire_rate?: string | null;
}

