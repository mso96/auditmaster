import type { Metadata } from "next";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Doküman Kütüphanesi",
};

export default function DokumanKutuphanesiPage() {
  return <ModulePage item={navItems[4]} />;
}
