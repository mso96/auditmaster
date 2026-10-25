"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatWhen, type AuditSummary } from "@/lib/audit";

export function AuditList() {
  const [audits, setAudits] = useState<AuditSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<AuditSummary[]>("/audits")
      .then((rows) => {
        if (!cancelled) {
          setAudits(rows);
          setLoading(false);
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "Liste alınamadı.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card>
      <CardContent className="px-0">
        {error ? (
          <p className="px-4 py-6 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-(--card-spacing)">Denetim</TableHead>
              <TableHead>Kapsam</TableHead>
              <TableHead>Risk</TableHead>
              <TableHead>Kayıt</TableHead>
              <TableHead className="pr-(--card-spacing)" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {audits.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-10 text-center text-muted-foreground"
                >
                  {loading
                    ? "Yükleniyor…"
                    : "Henüz denetim kaydı yok. RCM Oluşturucu kaydettiğinde burada görünür."}
                </TableCell>
              </TableRow>
            ) : (
              audits.map((audit) => (
                <TableRow key={audit.id}>
                  <TableCell className="pl-(--card-spacing) font-medium whitespace-normal">
                    {audit.title}
                  </TableCell>
                  <TableCell className="whitespace-normal">{audit.scope}</TableCell>
                  <TableCell>
                    {audit.rcm_id ? (
                      <Badge variant="secondary">{audit.risk_count}</Badge>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    {formatWhen(audit.rcm_updated_at ?? audit.created_at)}
                  </TableCell>
                  <TableCell className="pr-(--card-spacing) text-right">
                    <Link
                      href={`/rcm?audit=${audit.id}`}
                      className={buttonVariants({ variant: "outline", size: "sm" })}
                    >
                      RCM&apos;yi aç
                    </Link>
                    <Link href={`/test-planlari?audit=${audit.id}`}
                      className="ml-3 text-sm underline">
                      Test planı
                    </Link>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
