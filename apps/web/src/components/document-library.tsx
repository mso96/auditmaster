"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api } from "@/lib/api";
import {
  docTypeLabel,
  docTypeOptions,
  formatBytes,
  formatWhen,
  type DocType,
  type LibraryDocument,
} from "@/lib/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const fieldClassName =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function DocumentLibrary() {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [docType, setDocType] = useState<DocType>("prosedur");
  const [auditArea, setAuditArea] = useState("");
  const [fileKey, setFileKey] = useState(0);

  async function load() {
    const rows = await api<LibraryDocument[]>("/documents");
    setDocuments(rows);
  }

  useEffect(() => {
    const controller = new AbortController();
    api<LibraryDocument[]>("/documents")
      .then((rows) => {
        if (!controller.signal.aborted) {
          setDocuments(rows);
          setLoading(false);
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "Liste alınamadı.");
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("file");
    const file =
      fileInput instanceof HTMLInputElement ? fileInput.files?.[0] : undefined;
    if (!file) {
      setError("Bir dosya seçin.");
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);
    const body = new FormData();
    body.set("file", file);
    body.set("doc_type", docType);
    if (auditArea.trim()) {
      body.set("audit_area", auditArea.trim());
    }
    try {
      const created = await api<LibraryDocument>("/documents", {
        method: "POST",
        body,
      });
      setNotice(
        created.truncated
          ? `${created.filename} yüklendi; ilk ${created.chunk_count} parça saklandı.`
          : `${created.filename} yüklendi. ${created.chunk_count} parça üretildi.`,
      );
      setFileKey((value) => value + 1);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Yükleme başarısız.");
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(document: LibraryDocument) {
    const confirmed = window.confirm(
      `${document.filename} ve parçaları silinsin mi? Kaydedilmiş RCM alıntıları metin olarak durur.`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    try {
      await api<void>(`/documents/${document.id}`, { method: "DELETE" });
      setNotice(`${document.filename} silindi.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Silinemedi.");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Belge yükle</CardTitle>
          <CardDescription>
            PDF, DOCX, TXT veya Markdown. Metin sayfa ya da başlık bilgisiyle
            parçalanır ve aramaya eklenir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
            <label className="flex flex-col gap-1.5 text-sm font-medium md:col-span-2">
              Dosya
              <Input
                key={fileKey}
                name="file"
                type="file"
                accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
                required
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Tür
              <select
                className={fieldClassName}
                value={docType}
                onChange={(event) => setDocType(event.target.value as DocType)}
              >
                {docTypeOptions.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Denetim alanı
              <Input
                value={auditArea}
                onChange={(event) => setAuditArea(event.target.value)}
                placeholder="Satın Alma"
                maxLength={120}
              />
              <span className="text-xs font-normal text-muted-foreground">
                İsteğe bağlı. RCM araması bu alana göre daraltılabilir.
              </span>
            </label>
            <div className="md:col-span-2">
              <Button type="submit" disabled={uploading}>
                {uploading ? "Yükleniyor…" : "Kütüphaneye ekle"}
              </Button>
            </div>
          </form>
          {notice ? (
            <p className="mt-4 text-sm text-muted-foreground">{notice}</p>
          ) : null}
          {error ? (
            <p className="mt-4 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Kütüphane</CardTitle>
          <CardDescription>
            {loading ? "Belgeler yükleniyor." : `${documents.length} belge`}
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-(--card-spacing)">Belge</TableHead>
                <TableHead>Tür</TableHead>
                <TableHead>Denetim alanı</TableHead>
                <TableHead>Parça</TableHead>
                <TableHead>Yüklendi</TableHead>
                <TableHead className="pr-(--card-spacing)" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-10 text-center text-muted-foreground"
                  >
                    {loading ? "Yükleniyor…" : "Henüz belge yok."}
                  </TableCell>
                </TableRow>
              ) : (
                documents.map((document) => (
                  <TableRow key={document.id}>
                    <TableCell className="pl-(--card-spacing) whitespace-normal">
                      <div className="font-medium">{document.filename}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatBytes(document.byte_size)}
                        {document.truncated ? " · kısaltıldı" : ""}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {docTypeLabel[document.doc_type]}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      {document.audit_area ?? "—"}
                    </TableCell>
                    <TableCell>{document.chunk_count}</TableCell>
                    <TableCell className="whitespace-normal">
                      {formatWhen(document.created_at)}
                    </TableCell>
                    <TableCell className="pr-(--card-spacing) text-right">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onDelete(document)}
                      >
                        Sil
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
