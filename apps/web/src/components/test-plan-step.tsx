"use client";

import { CitationChips } from "@/components/citation-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { decisionLabel, type Citation } from "@/lib/audit";
import { methodLabels, ruleLabels, type PlanStep, type StepContent } from "@/lib/test-plan";

export const planInputClass =
  "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function TestPlanStep({
  step, index, disabled, onChange, onCitation,
}: {
  step: PlanStep;
  index: number;
  disabled: boolean;
  onChange: (step: PlanStep) => void;
  onCitation: (citation: Citation) => void;
}) {
  function edit(patch: Partial<StepContent>) {
    onChange({ ...step, ...patch, decision: "edited", citations: [], citation_status: "kaynaksız" });
  }
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Adım {index + 1}</CardTitle>
          <Badge variant={step.decision === "rejected" ? "destructive" : "secondary"}>
            {decisionLabel[step.decision]}
          </Badge>
        </div>
        <p className="text-sm leading-6"><strong>Risk:</strong> {step.risk_description}</p>
        <p className="text-sm leading-6"><strong>Kontrol:</strong> {step.control_description}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <fieldset disabled={disabled} className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Test amacı
            <textarea className={planInputClass} value={step.objective} required minLength={3}
              maxLength={2000} rows={3} onChange={(e) => edit({ objective: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Test yöntemi
            <select className={planInputClass} value={step.method}
              onChange={(e) => edit({ method: e.target.value as PlanStep["method"] })}>
              {Object.entries(methodLabels).map(([key, label]) =>
                <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium md:col-span-2">
            Prosedür adımı
            <textarea className={planInputClass} value={step.procedure} required minLength={3}
              maxLength={2000} rows={3} onChange={(e) => edit({ procedure: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Örneklem büyüklüğü önerisi ve gerekçesi
            <textarea className={planInputClass} value={step.sample_size} required minLength={3}
              maxLength={2000} rows={4} onChange={(e) => edit({ sample_size: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            İstenecek kanıtlar (her satırda bir belge/veri)
            <textarea className={planInputClass} value={step.evidence_requests.join("\n")}
              required maxLength={20000} rows={4}
              onChange={(e) => edit({ evidence_requests: e.target.value.split("\n") })} />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            İlgili veri analizi kuralı
            <select className={planInputClass} value={step.related_rule ?? ""}
              onChange={(e) => edit({ related_rule: (e.target.value || null) as PlanStep["related_rule"] })}>
              <option value="">İlişkili kural yok</option>
              {Object.entries(ruleLabels).map(([key, label]) =>
                <option key={key} value={key}>{label}</option>)}
            </select>
            <span className="text-xs font-normal text-muted-foreground">Yalnızca ilişkilendirme; kural çalıştırılmaz.</span>
          </label>
        </fieldset>
        <CitationChips citations={step.citations} status={step.citation_status} onOpen={onCitation} />
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={disabled} variant={step.decision === "accepted" ? "default" : "outline"}
            onClick={() => onChange({ ...step, decision: "accepted" })}>Kabul et</Button>
          <Button type="button" disabled={disabled} variant="outline"
            onClick={() => onChange({ ...step, decision: "rejected" })}>Reddet</Button>
          <Button type="button" disabled={disabled} variant="ghost"
            onClick={() => onChange({ ...step, decision: "pending" })}>Beklemeye al</Button>
        </div>
      </CardContent>
    </Card>
  );
}
