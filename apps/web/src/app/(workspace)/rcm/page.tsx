import type { Metadata } from "next";
import { Suspense } from "react";
import { ModulePage } from "@/components/module-page";
import { RcmGenerator } from "@/components/rcm-generator";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "RCM Oluşturucu",
};

export default function RcmPage() {
  return (
    <ModulePage item={navItems[1]} badge={null} showPlan={false} wide>
      <Suspense
        fallback={<p className="text-sm text-muted-foreground">Yükleniyor…</p>}
      >
        <RcmGenerator />
      </Suspense>
    </ModulePage>
  );
}
