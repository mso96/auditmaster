import type { Metadata } from "next";
import { ModulePage } from "@/components/module-page";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { navItems } from "@/lib/navigation";

export const metadata: Metadata = {
  title: "Denetimler",
};

export default function DenetimlerPage() {
  const item = navItems[0];

  return (
    <ModulePage item={item}>
      <Card>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-(--card-spacing)">Denetim</TableHead>
                <TableHead>Birim</TableHead>
                <TableHead>Dönem</TableHead>
                <TableHead className="pr-(--card-spacing)">Durum</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="py-10 text-center text-muted-foreground"
                >
                  Henüz denetim kaydı yok.
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </ModulePage>
  );
}
