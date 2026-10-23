"use client";

import { useState } from "react";
import { CitationChips } from "@/components/citation-chips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  controlTypeLabel,
  decisionLabel,
  levelLabel,
  natureLabel,
  type Citation,
  type Decision,
  type Level,
  type Risk,
} from "@/lib/audit";

const fieldClassName =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

const areaClassName =
  "min-h-20 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm leading-6 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function RcmTable({
  risks,
  onChange,
  onOpenCitation,
}: {
  risks: Risk[];
  onChange: (risks: Risk[]) => void;
  onOpenCitation: (citation: Citation) => void;
}) {
  const [draft, setDraft] = useState<Risk | null>(null);

  function setDecision(risk: Risk, decision: Decision) {
    onChange(
      risks.map((item) => (item.id === risk.id ? { ...item, decision } : item)),
    );
  }

  function applyDraft() {
    if (!draft) {
      return;
    }
    onChange(
      risks.map((item) =>
        item.id === draft.id ? { ...draft, decision: "edited" } : item,
      ),
    );
    setDraft(null);
  }

  return (
    <div className="flex flex-col gap-4">
      {draft ? (
        <form
          className="mx-4 flex flex-col gap-4 rounded-lg border p-4"
          onSubmit={(event) => {
            event.preventDefault();
            applyDraft();
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium">Riski düzenle</p>
            <Badge variant="outline">{draft.category}</Badge>
          </div>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Risk
            <textarea
              className={areaClassName}
              required
              minLength={3}
              value={draft.description}
              onChange={(event) =>
                setDraft({ ...draft, description: event.target.value })
              }
            />
          </label>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Kategori
              <input
                className={fieldClassName}
                required
                minLength={2}
                value={draft.category}
                onChange={(event) =>
                  setDraft({ ...draft, category: event.target.value })
                }
              />
            </label>
            <LevelField
              label="Olasılık"
              value={draft.likelihood}
              onChange={(likelihood) => setDraft({ ...draft, likelihood })}
            />
            <LevelField
              label="Etki"
              value={draft.impact}
              onChange={(impact) => setDraft({ ...draft, impact })}
            />
          </div>
          {draft.controls.map((control, index) => (
            <label
              key={control.id}
              className="flex flex-col gap-1.5 text-sm font-medium"
            >
              Kontrol {index + 1}
              <textarea
                className={areaClassName}
                required
                minLength={3}
                value={control.description}
                onChange={(event) => {
                  const controls = draft.controls.map((item) =>
                    item.id === control.id
                      ? { ...item, description: event.target.value }
                      : item,
                  );
                  setDraft({ ...draft, controls });
                }}
              />
            </label>
          ))}
          {draft.tests.map((test, index) => (
            <label
              key={test.id}
              className="flex flex-col gap-1.5 text-sm font-medium"
            >
              Test {index + 1}
              <textarea
                className={areaClassName}
                required
                minLength={3}
                value={test.description}
                onChange={(event) => {
                  const tests = draft.tests.map((item) =>
                    item.id === test.id
                      ? { ...item, description: event.target.value }
                      : item,
                  );
                  setDraft({ ...draft, tests });
                }}
              />
            </label>
          ))}
          <div className="flex gap-2">
            <Button type="submit" size="sm">
              Düzenlemeyi uygula
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setDraft(null)}
            >
              Vazgeç
            </Button>
          </div>
        </form>
      ) : null}

      <Table
        data-testid="rcm-table"
        className="min-w-[880px] [&_td]:align-top [&_td]:whitespace-normal"
      >
        <TableCaption>
          Öneridir. Kaynaksız satırlar dayanak pasaj taşımaz. Nihai karar
          denetçiye aittir.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[28%] pl-4">Risk</TableHead>
            <TableHead className="w-[28%]">Kontroller</TableHead>
            <TableHead className="w-[24%]">Testler</TableHead>
            <TableHead className="w-[20%] pr-4">Karar</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {risks.map((risk) => (
            <TableRow
              key={risk.id}
              className={risk.decision === "rejected" ? "opacity-60" : undefined}
              data-decision={risk.decision}
            >
              <TableCell className="pl-4">
                <div className="flex max-w-md flex-col gap-2">
                  <p className="leading-6">{risk.description}</p>
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="secondary">{risk.category}</Badge>
                    <Badge variant="outline">
                      Olasılık {levelLabel[risk.likelihood]}
                    </Badge>
                    <Badge variant="outline">Etki {levelLabel[risk.impact]}</Badge>
                  </div>
                  <CitationChips
                    citations={risk.citations}
                    status={risk.citation_status}
                    onOpen={onOpenCitation}
                  />
                </div>
              </TableCell>
              <TableCell>
                <ul className="flex max-w-md flex-col gap-3">
                  {risk.controls.map((control) => (
                    <li key={control.id} className="flex flex-col gap-1.5">
                      <p className="leading-6">{control.description}</p>
                      <div className="flex flex-wrap gap-1">
                        <Badge variant="outline">
                          {controlTypeLabel[control.control_type]}
                        </Badge>
                        <Badge variant="outline">{natureLabel[control.nature]}</Badge>
                      </div>
                      <CitationChips
                        citations={control.citations}
                        status={control.citation_status}
                        onOpen={onOpenCitation}
                      />
                    </li>
                  ))}
                </ul>
              </TableCell>
              <TableCell>
                <ul className="flex max-w-sm flex-col gap-3">
                  {risk.tests.map((test) => (
                    <li key={test.id} className="flex flex-col gap-1.5">
                      <p className="leading-6">{test.description}</p>
                      <CitationChips
                        citations={test.citations}
                        status={test.citation_status}
                        onOpen={onOpenCitation}
                      />
                    </li>
                  ))}
                </ul>
              </TableCell>
              <TableCell className="pr-4">
                <div className="flex flex-col gap-2">
                  <Badge
                    variant={
                      risk.decision === "rejected" ? "destructive" : "outline"
                    }
                  >
                    {decisionLabel[risk.decision]}
                  </Badge>
                  <div className="flex flex-wrap gap-1">
                    <Button
                      type="button"
                      size="xs"
                      variant={risk.decision === "accepted" ? "default" : "outline"}
                      onClick={() => setDecision(risk, "accepted")}
                    >
                      Kabul
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() => setDraft(structuredClone(risk))}
                    >
                      Düzenle
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant={risk.decision === "rejected" ? "destructive" : "outline"}
                      onClick={() => setDecision(risk, "rejected")}
                    >
                      Reddet
                    </Button>
                    {risk.decision !== "pending" ? (
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        onClick={() => setDecision(risk, "pending")}
                      >
                        Geri al
                      </Button>
                    ) : null}
                  </div>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function LevelField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Level;
  onChange: (value: Level) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium">
      {label}
      <select
        className={fieldClassName}
        value={value}
        onChange={(event) => onChange(event.target.value as Level)}
      >
        <option value="low">Düşük</option>
        <option value="medium">Orta</option>
        <option value="high">Yüksek</option>
      </select>
    </label>
  );
}
