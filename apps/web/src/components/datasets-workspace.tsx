"use client";

import { useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Dataset = {
  id: string;
  name: string;
  sheet: string | null;
  row_count: number;
  created_at: string;
};
type Column = {
  name: string;
  type: "number" | "date" | "text" | "boolean";
  null_count: number;
  distinct_count: number;
  min: string | number | null;
  max: string | number | null;
  top_values: { value: string; count: number }[];
};
type Preview = {
  columns: string[];
  rows: Record<string, string | number | boolean | null>[];
};
type Detail = { id: string; profile: { columns: Column[] }; preview: Preview };
const api = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const typeLabels = {
  number: "Sayı",
  date: "Tarih",
  text: "Metin",
  boolean: "Mantıksal",
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${api}${path}`, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new Error(
      "Sunucuya erişilemiyor. Bağlantınızı kontrol edip tekrar deneyin.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "İşlem tamamlanamadı. Lütfen tekrar deneyin.",
    );
  }
  return response.json();
}

function display(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Evet" : "Hayır";
  return String(value);
}

export function DatasetsWorkspace() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState("");
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [retry, setRetry] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    request<Dataset[]>("/datasets", { signal: controller.signal })
      .then(setDatasets)
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    Promise.all([
      request<Detail["profile"]>(`/datasets/${selected.id}/profile`, {
        signal: controller.signal,
      }),
      request<Preview>(`/datasets/${selected.id}/preview`, {
        signal: controller.signal,
      }),
    ])
      .then(([profile, preview]) => {
        if (!controller.signal.aborted)
          setDetail({ id: selected.id, profile, preview });
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setDetailError(e.message);
      });
    return () => controller.abort();
  }, [selected, retry]);

  function choose(candidate?: File) {
    if (uploading || !candidate) return;
    setError("");
    setNotice("");
    setSheet("");
    if (!/\.(csv|xlsx)$/i.test(candidate.name)) {
      setFile(null);
      setError("CSV veya XLSX dosyası seçin.");
      return;
    }
    if (candidate.size > 50 * 1024 * 1024) {
      setFile(null);
      setError("Dosya boyutu en fazla 50 MB olabilir.");
      return;
    }
    setFile(candidate);
  }

  function select(dataset: Dataset) {
    setDetail(null);
    setDetailError("");
    setSelected(dataset);
    setRetry((v) => v + 1);
  }

  async function upload() {
    if (!file || uploading) return;
    setUploading(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.append("file", file);
    if (/\.xlsx$/i.test(file.name) && sheet.trim())
      body.append("sheet", sheet.trim());
    try {
      const dataset = await request<Dataset>("/datasets", {
        method: "POST",
        body,
      });
      setDatasets((items) => [dataset, ...items]);
      select(dataset);
      setFile(null);
      setSheet("");
      if (input.current) input.current.value = "";
      setNotice("Dosya yüklendi. Önizleme ve sütun profili hazır.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yükleme tamamlanamadı.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Veri Analizi</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Excel veya CSV dosyanızı yükleyin; satırları ve sütunların veri
          kalitesini inceleyin.
        </p>
      </header>
      {error && (
        <p
          role="alert"
          className="rounded-lg border border-destructive p-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="rounded-lg border p-3 text-sm">
          {notice}
        </p>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Veri kümesi yükle</CardTitle>
          <CardDescription>
            CSV ve XLSX · En fazla 50 MB · Dosyalar kurum içindeki sunucuda
            saklanır.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            className="rounded-lg border-2 border-dashed p-6 text-center"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              choose(event.dataTransfer.files[0]);
            }}
          >
            <UploadCloud
              className="mx-auto mb-3 size-8 text-muted-foreground"
              aria-hidden
            />
            <label
              htmlFor="dataset-file"
              className="mb-3 block text-sm font-medium"
            >
              Dosyanızı buraya bırakın veya dosya seçin
            </label>
            <Input
              ref={input}
              id="dataset-file"
              type="file"
              accept=".csv,.xlsx"
              disabled={uploading}
              className="sr-only"
              onChange={(event) => choose(event.target.files?.[0])}
            />
            <Button type="button" variant="outline" disabled={uploading} onClick={() => input.current?.click()}>
              Dosya seç
            </Button>
            {file && (
              <p className="mt-3 break-all text-sm">
                {file.name} ·{" "}
                {(file.size / 1024).toLocaleString("tr-TR", {
                  maximumFractionDigits: 1,
                })}{" "}
                KB
              </p>
            )}
          </div>
          {file && /\.xlsx$/i.test(file.name) && (
            <div className="max-w-md space-y-2">
              <label htmlFor="dataset-sheet" className="text-sm font-medium">
                Çalışma sayfası adı (isteğe bağlı)
              </label>
              <Input
                id="dataset-sheet"
                value={sheet}
                onChange={(event) => setSheet(event.target.value)}
                disabled={uploading}
                placeholder="Boş bırakırsanız ilk sayfa alınır"
              />
            </div>
          )}
          <Button onClick={upload} disabled={!file || uploading || loading}>
            {uploading ? "Yükleniyor ve profilleniyor…" : "Yükle ve incele"}
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Veri kümeleri</CardTitle>
            <CardDescription>
              İncelemek için bir veri kümesi seçin.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            disabled={loading || uploading}
            onClick={() => {
              setLoading(true);
              setError("");
              setRefresh((v) => v + 1);
            }}
          >
            Yenile
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p role="status">Veri kümeleri yükleniyor…</p>
          ) : datasets.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Henüz veri kümesi yok. İlk dosyanızı yükleyerek başlayın.
            </p>
          ) : (
            <Table>
              <TableCaption>Yüklenen dosyalar</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Dosya</TableHead>
                  <TableHead>Sayfa</TableHead>
                  <TableHead>Satır</TableHead>
                  <TableHead>Yükleme tarihi</TableHead>
                  <TableHead>İşlem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasets.map((dataset) => (
                  <TableRow
                    key={dataset.id}
                    data-state={
                      selected?.id === dataset.id ? "selected" : undefined
                    }
                  >
                    <TableCell
                      className="max-w-72 truncate"
                      title={dataset.name}
                    >
                      {dataset.name}
                    </TableCell>
                    <TableCell>{dataset.sheet ?? "—"}</TableCell>
                    <TableCell>
                      {dataset.row_count.toLocaleString("tr-TR")}
                    </TableCell>
                    <TableCell>
                      {new Date(dataset.created_at).toLocaleString("tr-TR")}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`${dataset.name} dosyasını incele`}
                        onClick={() => select(dataset)}
                      >
                        İncele
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      {selected && (
        <section
          aria-label="Veri kümesi ayrıntıları"
          className="min-w-0 space-y-4"
        >
          <h2 className="break-all text-xl font-semibold">{selected.name}</h2>
          {detailError ? (
            <div role="alert" className="space-y-2">
              <p className="text-destructive">{detailError}</p>
              <Button
                variant="outline"
                onClick={() => {
                  setDetailError("");
                  setRetry((v) => v + 1);
                }}
              >
                Tekrar dene
              </Button>
            </div>
          ) : detail?.id !== selected.id ? (
            <p role="status">Önizleme ve sütun profili yükleniyor…</p>
          ) : (
            <>
              <Card className="min-w-0">
                <CardHeader>
                  <CardTitle>Önizleme</CardTitle>
                  <CardDescription>
                    İlk {detail.preview.rows.length} satır · Toplam{" "}
                    {selected.row_count.toLocaleString("tr-TR")} satır
                  </CardDescription>
                </CardHeader>
                <CardContent className="min-w-0">
                  <Table>
                    <TableCaption>Kaynak dosyanın ilk 100 satırı</TableCaption>
                    <TableHeader>
                      <TableRow>
                        {detail.preview.columns.map((column) => (
                          <TableHead key={column}>{column}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.preview.rows.map((row, index) => (
                        <TableRow key={index}>
                          {detail.preview.columns.map((column) => (
                            <TableCell
                              key={column}
                              className="max-w-80 truncate"
                              title={display(row[column])}
                            >
                              {display(row[column])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
              <Card className="min-w-0">
                <CardHeader>
                  <CardTitle>Sütun profili</CardTitle>
                  <CardDescription>
                    Türler dolu değerlerden çıkarılır. Boş değerler benzersiz
                    değer sayısına dahil edilmez.
                  </CardDescription>
                </CardHeader>
                <CardContent className="min-w-0">
                  <Table>
                    <TableCaption>Sütun türleri ve veri kalitesi</TableCaption>
                    <TableHeader>
                      <TableRow>
                        {[
                          "Sütun",
                          "Tür",
                          "Boş",
                          "Benzersiz",
                          "En küçük",
                          "En büyük",
                          "En sık 5 değer",
                        ].map((label) => (
                          <TableHead key={label}>{label}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.profile.columns.map((column) => (
                        <TableRow key={column.name}>
                          <TableCell>{column.name}</TableCell>
                          <TableCell>
                            <Badge variant="secondary">
                              {typeLabels[column.type]}
                            </Badge>
                          </TableCell>
                          <TableCell>{column.null_count}</TableCell>
                          <TableCell>{column.distinct_count}</TableCell>
                          <TableCell>{display(column.min)}</TableCell>
                          <TableCell>{display(column.max)}</TableCell>
                          <TableCell className="max-w-96 whitespace-normal break-words">
                            {column.top_values
                              .map(({ value, count }) => `${value} (${count})`)
                              .join(" · ") || "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </>
          )}
        </section>
      )}
    </div>
  );
}
