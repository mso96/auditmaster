"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { RcmTable } from "@/components/rcm-table";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { api, apiBaseUrl } from "@/lib/api";
import {
  docTypeLabel,
  type AuditDetail,
  type Citation,
  type DocType,
  type GenerateResponse,
  type ModelMode,
  type Risk,
} from "@/lib/audit";

const areaClassName =
  "min-h-24 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm leading-6 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

type SaveResponse = {
  audit_id: string;
  title: string;
  rcm: { id: string; risks: Risk[]; model_mode: ModelMode };
};

export function RcmGenerator() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auditFromUrl = searchParams.get("audit");

  const [scope, setScope] = useState("");
  const [notes, setNotes] = useState("");
  const [area, setArea] = useState("");
  const [risks, setRisks] = useState<Risk[]>([]);
  const [passageCount, setPassageCount] = useState(0);
  const [modelMode, setModelMode] = useState<ModelMode | null>(null);
  const [auditId, setAuditId] = useState<string | null>(auditFromUrl);
  const [rcmId, setRcmId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [loadedAudit, setLoadedAudit] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<{ llm?: { mode?: ModelMode } }>("/health")
      .then((body) => {
        if (!cancelled && (body.llm?.mode === "fake" || body.llm?.mode === "openai")) {
          setModelMode((current) => current ?? body.llm?.mode ?? null);
        }
      })
      .catch(() => {
        // The form still works; generation will surface a connection error.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!auditFromUrl || loadedAudit === auditFromUrl) {
      return;
    }
    let cancelled = false;
    api<AuditDetail>(`/audits/${auditFromUrl}`)
      .then((audit) => {
        if (cancelled) {
          return;
        }
        setLoadedAudit(auditFromUrl);
        setAuditId(audit.id);
        setScope(audit.scope);
        if (audit.rcm) {
          setNotes(audit.rcm.process_notes ?? "");
          setArea(audit.rcm.audit_area ?? "");
          setRisks(audit.rcm.risks);
          setPassageCount(audit.rcm.passage_count);
          setModelMode(audit.rcm.model_mode);
          setRcmId(audit.rcm.id);
          setDirty(false);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Denetim açılamadı.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auditFromUrl, loadedAudit]);

  async function onGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (dirty && risks.length > 0) {
      const confirmed = window.confirm(
        "Kaydedilmemiş kararlar var. Yeni öneri bunları değiştirir.",
      );
      if (!confirmed) {
        return;
      }
    }
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const body = await api<GenerateResponse>("/rcm/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope: scope.trim(),
          process_notes: notes.trim() || null,
          audit_area: area.trim() || null,
        }),
      });
      setRisks(body.risks);
      setPassageCount(body.passage_count);
      setModelMode(body.model_mode);
      setDirty(true);
      setNotice(
        body.risks.length === 0
          ? "Model risk önermedi."
          : `${body.risks.length} risk önerildi, ${body.passage_count} pasaj tarandı.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Öneri üretilemedi.");
    } finally {
      setGenerating(false);
    }
  }

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      const saved = await api<SaveResponse>("/rcms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audit_id: auditId,
          scope: scope.trim(),
          process_notes: notes.trim() || null,
          audit_area: area.trim() || null,
          passage_count: passageCount,
          risks,
        }),
      });
      setAuditId(saved.audit_id);
      setLoadedAudit(saved.audit_id);
      setRcmId(saved.rcm.id);
      setRisks(saved.rcm.risks);
      setModelMode(saved.rcm.model_mode);
      setDirty(false);
      setNotice("Denetim kaydedildi. Kararlar bu RCM ile birlikte durur.");
      router.replace(`/rcm?audit=${saved.audit_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Kayıt başarısız.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Kapsam</CardTitle>
          <CardDescription>
            Model yalnızca önerir. Her satırın dayanağı bir alıntıdır; alıntısı
            olmayan satır Kaynaksız olarak işaretlenir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={onGenerate}>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Denetim kapsamı
              <Input
                id="audit-scope"
                value={scope}
                onChange={(event) => setScope(event.target.value)}
                placeholder="Satın alma denetimi"
                required
                minLength={3}
                maxLength={500}
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Süreç notları
              <textarea
                className={areaClassName}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="İsteğe bağlı. Örneğin eşik tutar veya uygulanan teklif kuralı."
                maxLength={4000}
              />
            </label>
            <label className="flex max-w-sm flex-col gap-1.5 text-sm font-medium">
              Denetim alanı
              <Input
                value={area}
                onChange={(event) => setArea(event.target.value)}
                placeholder="Satın Alma"
                maxLength={120}
              />
              <span className="text-xs font-normal text-muted-foreground">
                Boş bırakılırsa kütüphanenin tamamı taranır.
              </span>
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={generating}>
                {generating ? "Öneri hazırlanıyor…" : "RCM öner"}
              </Button>
              {modelMode === "fake" ? (
                <Badge variant="outline">Deterministik örnek model</Badge>
              ) : null}
            </div>
          </form>
          {modelMode === "fake" ? (
            <p className="mt-3 max-w-3xl text-xs leading-5 text-muted-foreground">
              Örnek model ağ çağrısı yapmaz. Aynı ekran, OpenAI uyumlu bir uç
              tanımlandığında o modeli kullanır.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}

      {risks.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Risk kontrol matrisi</CardTitle>
            <CardDescription>
              {passageCount} pasaj tarandı. Satırları kabul edin, düzeltin veya
              reddedin; sonra denetimi kaydedin.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <RcmTable
              risks={risks}
              onChange={(next) => {
                setRisks(next);
                setDirty(true);
              }}
              onOpenCitation={setCitation}
            />
            <div className="flex flex-wrap items-center gap-3 px-4 pt-4">
              <Button type="button" onClick={onSave} disabled={saving}>
                {saving ? "Kaydediliyor…" : "Denetimi kaydet"}
              </Button>
              {rcmId && !dirty ? (
                <a
                  className={buttonVariants({ variant: "outline" })}
                  href={`${apiBaseUrl()}/rcms/${rcmId}/export`}
                >
                  Excel indir
                </a>
              ) : null}
              {dirty ? (
                <span className="text-xs text-muted-foreground">
                  Kaydedilmemiş değişiklik var.
                </span>
              ) : null}
              <Link
                href="/denetimler"
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
              >
                Denetimler
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Sheet open={citation !== null} onOpenChange={(open) => !open && setCitation(null)}>
        <SheetContent className="sm:max-w-md" data-testid="citation-sheet">
          {citation ? <CitationBody citation={citation} /> : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function CitationBody({ citation }: { citation: Citation }) {
  const docType = docTypeLabel[citation.doc_type as DocType] ?? citation.doc_type;
  return (
    <>
      <SheetHeader>
        <SheetTitle>Kaynak alıntı</SheetTitle>
        <SheetDescription>
          {docType}
          {citation.page ? ` · Sayfa ${citation.page}` : " · Sayfa bilgisi yok"}
          {citation.section ? ` · ${citation.section}` : ""}
        </SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-6">
        <p className="text-sm font-medium">{citation.document_name}</p>
        <blockquote className="border-l-2 border-primary/40 pl-3 text-sm leading-6">
          {citation.snippet}
        </blockquote>
        <div>
          <p className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Pasaj
          </p>
          <p className="text-sm leading-6 whitespace-pre-wrap text-muted-foreground">
            <HighlightedPassage passage={citation.passage} snippet={citation.snippet} />
          </p>
        </div>
        <p className="text-xs leading-5 text-muted-foreground">
          Bu alıntı önerinin dayanağıdır. Karar denetçiye aittir.
        </p>
      </div>
    </>
  );
}

function HighlightedPassage({
  passage,
  snippet,
}: {
  passage: string;
  snippet: string;
}) {
  const index = passage.indexOf(snippet);
  if (index < 0) {
    return passage;
  }
  return (
    <>
      {passage.slice(0, index)}
      <mark className="bg-primary/15 text-foreground">{snippet}</mark>
      {passage.slice(index + snippet.length)}
    </>
  );
}
