export type DocType =
  | "gecmis_denetim_raporu"
  | "bulgu"
  | "prosedur"
  | "standart"
  | "iyi_uygulama";

export type Level = "low" | "medium" | "high";
export type CitationStatus = "kaynaklı" | "kaynaksız";
export type Decision = "pending" | "accepted" | "edited" | "rejected";
export type ModelMode = "fake" | "openai";

export type Citation = {
  chunk_id: string;
  document_id: string;
  document_name: string;
  doc_type: string;
  page: number | null;
  section: string | null;
  snippet: string;
  passage: string;
};

export type Control = {
  id: string;
  description: string;
  control_type: "preventive" | "detective";
  nature: "manual" | "automated";
  citations: Citation[];
  citation_status: CitationStatus;
};

export type AuditTest = {
  id: string;
  description: string;
  citations: Citation[];
  citation_status: CitationStatus;
};

export type Risk = {
  id: string;
  description: string;
  category: string;
  likelihood: Level;
  impact: Level;
  controls: Control[];
  tests: AuditTest[];
  citations: Citation[];
  citation_status: CitationStatus;
  decision: Decision;
};

export type LibraryDocument = {
  id: string;
  filename: string;
  doc_type: DocType;
  audit_area: string | null;
  byte_size: number;
  chunk_count: number;
  truncated: boolean;
  created_at: string;
};

export type GenerateResponse = {
  scope: string;
  process_notes: string | null;
  audit_area: string | null;
  model_mode: ModelMode;
  passage_count: number;
  risks: Risk[];
};

export type RcmRecord = {
  id: string;
  audit_id: string;
  scope: string;
  process_notes: string | null;
  audit_area: string | null;
  model_mode: ModelMode;
  passage_count: number;
  risks: Risk[];
  created_at: string;
  updated_at: string;
};

export type AuditSummary = {
  id: string;
  title: string;
  scope: string;
  created_at: string;
  rcm_id: string | null;
  rcm_updated_at: string | null;
  risk_count: number;
};

export type AuditDetail = {
  id: string;
  title: string;
  scope: string;
  created_at: string;
  rcm: RcmRecord | null;
};

export const docTypeLabel: Record<DocType, string> = {
  gecmis_denetim_raporu: "Geçmiş denetim raporu",
  bulgu: "Bulgu",
  prosedur: "Prosedür",
  standart: "Standart",
  iyi_uygulama: "İyi uygulama",
};

export const docTypeOptions = Object.entries(docTypeLabel) as [DocType, string][];

export const levelLabel: Record<Level, string> = {
  low: "Düşük",
  medium: "Orta",
  high: "Yüksek",
};

export const controlTypeLabel = {
  preventive: "Önleyici",
  detective: "Saptayıcı",
} as const;

export const natureLabel = {
  manual: "Manuel",
  automated: "Otomatik",
} as const;

export const decisionLabel: Record<Decision, string> = {
  pending: "Bekliyor",
  accepted: "Kabul",
  edited: "Düzenlendi",
  rejected: "Reddedildi",
};

export function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  return `${(size / 1024).toFixed(1)} KB`;
}
