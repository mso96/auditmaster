import type { Metadata } from "next";
import { Suspense } from "react";
import { TestPlanWorkspace } from "@/components/test-plan-workspace";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Test Planları",
};

export default function TestPlanlariPage() {
  return (
    <ModulePage item={navItems[2]} badge={null} showPlan={false} wide>
      <Suspense fallback={<p>Yükleniyor…</p>}>
        <TestPlanWorkspace />
      </Suspense>
    </ModulePage>
  );
}
