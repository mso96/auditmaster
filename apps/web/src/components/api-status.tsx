"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "ok" | "down";

function apiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return configured.replace(/\/$/, "");
}

const label: Record<Status, string> = {
  checking: "API kontrol ediliyor",
  ok: "API hazır",
  down: "API erişilemiyor",
};

const dot: Record<Status, string> = {
  checking: "bg-muted-foreground/40",
  ok: "bg-emerald-600",
  down: "bg-destructive",
};

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${apiBaseUrl()}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error("health check failed");
        }
        setStatus("ok");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setStatus("down");
      });

    return () => controller.abort();
  }, []);

  return (
    <p className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className={`size-1.5 rounded-full ${dot[status]}`} aria-hidden />
      <span>{label[status]}</span>
    </p>
  );
}
