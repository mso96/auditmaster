"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { ApiStatus } from "@/components/api-status";
import { AppSidebar } from "@/components/app-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { findNavItem } from "@/lib/navigation";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const current = findNavItem(pathname);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4">
          <SidebarTrigger />
          <Separator orientation="vertical" className="mx-1 h-4" />
          <p className="truncate text-sm text-muted-foreground">
            {current?.title ?? "AuditMaster"}
          </p>
          <div className="ml-auto flex items-center gap-3">
            <ApiStatus />
            <ThemeToggle />
          </div>
        </header>
        <div className="flex flex-1 flex-col px-6 py-8">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
