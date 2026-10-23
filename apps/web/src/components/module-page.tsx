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
}: {
  item: NavItem;
  children?: ReactNode;
}) {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{item.title}</h1>
          <Badge variant="outline">Hazırlanıyor</Badge>
        </div>
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          {item.description}
        </p>
      </div>
      {children}
      <Card>
        <CardHeader>
          <CardTitle>Planlanan kapsam</CardTitle>
          <CardDescription>Bu ekran henüz veri üretmez.</CardDescription>
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
      </Card>
      <p className="border-t pt-4 text-xs leading-5 text-muted-foreground">
        Yapay zeka yalnızca öneri üretir. Her çıktı, dayandığı kaynakla birlikte
        gösterilir. Nihai karar denetçiye aittir.
      </p>
    </div>
  );
}
