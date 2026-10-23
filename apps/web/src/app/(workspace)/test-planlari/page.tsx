import type { Metadata } from "next";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Test Planları",
};

export default function TestPlanlariPage() {
  return <ModulePage item={navItems[2]} />;
}
