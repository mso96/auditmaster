import type { Citation, CitationStatus, Decision, ModelMode } from "@/lib/audit";

export const methodLabels = {
  inspection: "İnceleme",
  observation: "Gözlem",
  reperformance: "Yeniden uygulama",
  analytical: "Analitik",
} as const;

export const ruleLabels = {
  exact_duplicate: "Aynı ödemenin tekrarı",
  fuzzy_duplicate: "Olası mükerrer ödeme",
  shared_iban: "Ortak IBAN",
  amount_pattern: "Yuvarlak / onay sınırına yakın tutar",
  non_working_day: "Tatil gününde kayıt",
  segregation_of_duties: "Görevler ayrılığı",
  vendor_outlier: "Tedarikçi bazında aykırı tutar",
  benford: "Benford ilk basamak",
} as const;

export type StepContent = {
  objective: string;
  method: keyof typeof methodLabels;
  procedure: string;
  sample_size: string;
  evidence_requests: string[];
  related_rule: keyof typeof ruleLabels | null;
};

export type PlanStep = StepContent & {
  id: string;
  risk_id: string;
  control_id: string;
  risk_description: string;
  control_description: string;
  decision: Decision;
  citations: Citation[];
  citation_status: CitationStatus;
};

export type TestPlan = {
  audit_id: string;
  rcm_id: string;
  rcm_updated_at: string;
  revision: number;
  model_mode: ModelMode;
  steps: PlanStep[];
  updated_at: string;
  stale: boolean;
};
