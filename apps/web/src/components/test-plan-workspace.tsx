"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { TestPlanStep, planInputClass } from "@/components/test-plan-step";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, apiBaseUrl } from "@/lib/api";
import { formatWhen, type AuditDetail, type AuditSummary, type Citation } from "@/lib/audit";
import type { TestPlan } from "@/lib/test-plan";

export function TestPlanWorkspace() {
  const params = useSearchParams();
  const auditId = params.get("audit") ?? "";
  return <PlanSession key={auditId} auditId={auditId} />;
}

function PlanSession({ auditId }: { auditId: string }) {
  const router = useRouter();
  const [audits, setAudits] = useState<AuditSummary[]>([]);
  const [selection, setSelection] = useState(auditId);
  const [audit, setAudit] = useState<AuditDetail | null>(null);
  const [plan, setPlan] = useState<TestPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    Promise.all([
      api<AuditSummary[]>("/audits", options),
      auditId ? api<AuditDetail>(`/audits/${auditId}`, options) : Promise.resolve(null),
      auditId ? api<TestPlan | null>(`/audits/${auditId}/test-plan`, options) : Promise.resolve(null),
    ]).then(([list, detail, saved]) => {
      setAudits(list);
      setAudit(detail);
      setPlan(saved);
      setLoading(false);
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "Plan açılamadı.");
        setLoading(false);
      }
    });
    return () => controller.abort();
  }, [auditId]);

  useEffect(() => {
    if (!dirty) return;
    const preventLoss = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", preventLoss);
    return () => window.removeEventListener("beforeunload", preventLoss);
  }, [dirty]);

  function openAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (dirty && !window.confirm("Kaydedilmemiş değişiklikler var. Başka denetime geçilsin mi?")) return;
    router.push(`/test-planlari?audit=${selection}`);
  }

  async function generate() {
    if (plan && !window.confirm("Yeni öneriler mevcut planın ve kararların yerini alacak. Devam edilsin mi?")) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const saved = await api<TestPlan>(`/audits/${auditId}/test-plan/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: plan?.revision ?? 0 }),
      });
      setPlan(saved); setDirty(false);
      setNotice("Öneri taslağı kaydedildi. Her adımı inceleyip kararlarınızı kaydedin.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Öneri üretilemedi.");
    } finally { setBusy(false); }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!plan) return;
    const invalid = plan.steps.some((step) => {
      const evidence = step.evidence_requests.map((value) => value.trim()).filter(Boolean);
      const texts = [step.objective, step.procedure, step.sample_size, ...evidence];
      return evidence.length < 1 || evidence.length > 10 ||
        texts.some((value) => value.trim().length < 3 || value.trim().length > 2000);
    });
    if (invalid) {
      setError("Metin alanları 3–2000 karakter olmalıdır. Her adım için 1–10 kanıt girin.");
      return;
    }
    setBusy(true); setError(null); setNotice(null);
    try {
      const saved = await api<TestPlan>(`/audits/${auditId}/test-plan`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_revision: plan.revision,
          steps: plan.steps.map((s) => ({
            id: s.id, objective: s.objective, method: s.method, procedure: s.procedure,
            sample_size: s.sample_size, related_rule: s.related_rule, decision: s.decision,
            evidence_requests: s.evidence_requests.map((v) => v.trim()).filter(Boolean),
          })),
        }),
      });
      setPlan(saved); setDirty(false); setNotice("Kararlar ve düzenlemeler kaydedildi.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Plan kaydedilemedi.");
    } finally { setBusy(false); }
  }

  const accepted = audit?.rcm?.risks.filter((r) => r.decision === "accepted")
    .reduce((count, r) => count + r.controls.length, 0) ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Denetim ve kabul edilmiş kontroller</CardTitle>
          <CardDescription>Yalnızca kaydedilmiş RCM&apos;de “Kabul” durumundaki satırlar kullanılır.
            Hiçbir test veya analiz otomatik çalıştırılmaz.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form onSubmit={openAudit} className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-60 flex-1 flex-col gap-1.5 text-sm font-medium">
              Denetim
              <select className={planInputClass} value={selection} required disabled={busy || loading}
                onChange={(e) => setSelection(e.target.value)}>
                <option value="">Denetim seçin</option>
                {audits.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
              </select>
            </label>
            <Button disabled={busy || loading || !selection} type="submit">Denetimi aç</Button>
          </form>
          {loading ? <p role="status">Yükleniyor…</p> : null}
          {!loading && audits.length === 0 ? <p className="text-sm">Henüz denetim yok. Önce <Link className="underline" href="/rcm">RCM oluşturup kaydedin</Link>.</p> : null}
          {audit ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm">{accepted} kabul edilmiş kontrol</span>
              <Button type="button" disabled={busy || accepted === 0} onClick={generate}>
                {busy ? "İşlem sürüyor…" : "Test öner ve taslağı kaydet"}
              </Button>
              <Link className="text-sm underline" href={`/rcm?audit=${auditId}`}>RCM&apos;yi aç</Link>
            </div>
          ) : null}
          {audit && accepted === 0 ? <p className="text-sm text-muted-foreground">Öneri için RCM&apos;de kontrol içeren bir satırı kabul edip kaydedin. “Düzenlendi” ve “Bekliyor” satırları henüz onaylanmış sayılmaz.</p> : null}
        </CardContent>
      </Card>

      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {notice ? <p role="status" className="text-sm">{notice}</p> : null}
      {plan ? (
        <form onSubmit={save} className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold">Test planı · {plan.steps.length} adım</h2>
            {plan.model_mode === "fake" ? <Badge variant="outline">Örnek öneriler</Badge> : null}
            <span className="text-xs text-muted-foreground">Son kayıt: {formatWhen(plan.updated_at)}</span>
          </div>
          {plan.stale ? <p role="alert" className="rounded-lg border border-destructive p-4 text-sm">
            RCM bu plandan sonra değişti. Eski planı inceleyebilirsiniz; kaydetmek veya dışa aktarmak için güncel kontrollerden yeniden öneri üretin.
          </p> : null}
          <p className="text-sm text-muted-foreground">
            Alanları düzenleyebilir, her adımı kabul edebilir veya reddedebilirsiniz.
            Düzenlenen metin yeniden kaynak doğrulaması gerektirdiğinden Kaynaksız işaretlenir.
            Örneklem büyüklüğü öneridir; evren ve riske göre denetçi belirler.
          </p>
          {plan.steps.map((step, index) => (
            <TestPlanStep key={step.id} step={step} index={index} disabled={busy || plan.stale}
              onCitation={setCitation} onChange={(next) => {
                setPlan((current) => current ? { ...current, steps: current.steps.map((s) => s.id === next.id ? next : s) } : current);
                setDirty(true); setNotice(null);
              }} />
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={busy || !dirty || plan.stale}>Kararları kaydet</Button>
            {!dirty && !plan.stale && !busy ? <a className={buttonVariants({ variant: "outline" })}
              href={`${apiBaseUrl()}/audits/${auditId}/test-plan/export`}>Excel indir</a> : null}
            {dirty ? <span className="text-sm text-muted-foreground">Kaydedilmemiş değişiklikler var. Dışa aktarmadan önce kaydedin.</span> : null}
          </div>
        </form>
      ) : null}
      <Sheet open={citation !== null} onOpenChange={(open) => !open && setCitation(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Kaynak alıntı</SheetTitle>
            <SheetDescription>{citation?.document_name}
              {citation?.page ? ` · Sayfa ${citation.page}` : ""}
              {citation?.section ? ` · ${citation.section}` : ""}</SheetDescription>
          </SheetHeader>
          <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-6">
            <blockquote className="border-l-2 pl-3 text-sm leading-6">{citation?.snippet}</blockquote>
            <p className="text-sm leading-6 whitespace-pre-wrap text-muted-foreground">{citation?.passage}</p>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
