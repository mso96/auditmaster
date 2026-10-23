import type { Metadata } from "next";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "RCM Oluşturucu",
};

export default function RcmPage() {
  return <ModulePage item={navItems[1]} />;
}
