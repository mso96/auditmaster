import type { Metadata } from "next";
import { AuditList } from "@/components/audit-list";
import { ModulePage } from "@/components/module-page";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Denetimler",
};

export default function DenetimlerPage() {
  return (
    <ModulePage
      item={navItems[0]}
      badge="Kısmi"
      planNote="Dönem, birim ve sorumlu denetçi henüz tutulmuyor. Liste, kaydedilen RCM denetimlerinden gelir."
    >
      <AuditList />
    </ModulePage>
  );
}
