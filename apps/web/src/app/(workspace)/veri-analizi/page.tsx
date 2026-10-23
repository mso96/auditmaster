import type { Metadata } from "next";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Veri Analizi",
};

export default function VeriAnaliziPage() {
  return <ModulePage item={navItems[3]} />;
}
