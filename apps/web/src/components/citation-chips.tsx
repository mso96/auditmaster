"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Citation, CitationStatus } from "@/lib/audit";

export function CitationChips({
  citations,
  status,
  onOpen,
}: {
  citations: Citation[];
  status: CitationStatus;
  onOpen: (citation: Citation) => void;
}) {
  if (status === "kaynaksız" || citations.length === 0) {
    return <Badge variant="destructive">Kaynaksız</Badge>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {citations.map((citation) => {
        const where = [
          citation.document_name,
          citation.page ? `s. ${citation.page}` : null,
          citation.section,
        ]
          .filter(Boolean)
          .join(" · ");
        return (
          <Button
            key={`${citation.chunk_id}-${citation.snippet.slice(0, 24)}`}
            type="button"
            variant="outline"
            size="xs"
            className="max-w-56"
            onClick={() => onOpen(citation)}
          >
            <span className="truncate">{where}</span>
          </Button>
        );
      })}
    </span>
  );
}
