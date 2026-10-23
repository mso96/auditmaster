import type { ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { NavItem } from "@/lib/navigation";

export function ModulePage({
  item,
  children,
  badge = "Hazırlanıyor",
  showPlan = true,
  planNote = "Bu ekran henüz veri üretmez.",
  wide = false,
}: {
  item: NavItem;
  children?: ReactNode;
  badge?: string | null;
  showPlan?: boolean;
  planNote?: string;
  wide?: boolean;
}) {
  return (
    <div
      className={`mx-auto flex w-full flex-col gap-8 ${wide ? "max-w-7xl" : "max-w-5xl"}`}
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{item.title}</h1>
          {badge ? <Badge variant="outline">{badge}</Badge> : null}
        </div>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          {item.description}
        </p>
      </div>
      {children}
      {showPlan ? <Card>
        <CardHeader>
          <CardTitle>Planlanan kapsam</CardTitle>
          <CardDescription>{planNote}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2.5">
            {item.points.map((point) => (
              <li key={point} className="flex gap-3 text-sm leading-6">
                <span
                  className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/80"
                  aria-hidden
                />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card> : null}
      <p className="border-t pt-4 text-xs leading-5 text-muted-foreground">
        Yapay zeka yalnızca öneri üretir. Her çıktı, dayandığı kaynakla birlikte
        gösterilir. Nihai karar denetçiye aittir.
      </p>
    </div>
  );
}
