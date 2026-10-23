import type { Metadata } from "next";
import { DatasetsWorkspace } from "@/components/datasets-workspace";

export const metadata: Metadata = {
  title: "Veri Analizi",
};

export default function VeriAnaliziPage() {
  return <DatasetsWorkspace />;
}
