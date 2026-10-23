import {
  BarChart3,
  ClipboardList,
  Library,
  ListChecks,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  title: string;
  href: string;
  icon: LucideIcon;
  description: string;
  points: string[];
};

export const navItems: NavItem[] = [
  {
    title: "Denetimler",
    href: "/denetimler",
    icon: ClipboardList,
    description:
      "Planlanan ve devam eden denetim çalışmaları burada listelenecek. Bu ekran henüz kayıt tutmuyor.",
    points: [
      "Denetim, birim, dönem ve durum alanları",
      "Çalışma kağıtlarına geçiş",
      "Sorumlu denetçi bilgisi",
    ],
  },
  {
    title: "RCM Oluşturucu",
    href: "/rcm",
    icon: ShieldCheck,
    description:
      "Geçmiş denetim raporları, bulgular, şirket prosedürleri ve denetim standartlarından risk, ilişkili kontroller ve önerilen denetim testleri üretilecek. Her satır kaynak gösterimi taşıyacak.",
    points: [
      "Kapsama alınacak belgelerin seçimi",
      "Risk, kontrol ve test önerileri",
      "Her önerinin dayandığı kaynak alıntısı",
    ],
  },
  {
    title: "Test Planları",
    href: "/test-planlari",
    icon: ListChecks,
    description:
      "Her risk ve kontrol için hangi verinin gerektiği ve izlenecek adımlar öneri olarak sunulacak. Uygulama kararı denetçidedir.",
    points: [
      "Risk ve kontrole bağlı öneriler",
      "Gerekli veri ve uygulama adımları",
      "Denetçinin kabul veya düzeltme kararı",
    ],
  },
  {
    title: "Veri Analizi",
    href: "/veri-analizi",
    icon: BarChart3,
    description:
      "Yüklenen Excel ve CSV dosyaları üzerinde mükerrer ödeme ve anomali kontrolleri daha sonra bu ekrandan çalıştırılacak. Salt okunur veritabanı bağlantısı sonraki aşamadadır.",
    points: [
      "Excel ve CSV yükleme",
      "Mükerrer ödeme ve anomali kontrolleri",
      "Sonuçların dayanaklarıyla incelenmesi",
    ],
  },
  {
    title: "Doküman Kütüphanesi",
    href: "/dokuman-kutuphanesi",
    icon: Library,
    description:
      "Denetim raporları, prosedürler ve standartlar burada toplanacak. RCM üretimi bu belgelerdeki pasajlara dayanacak.",
    points: [
      "Belge yükleme ve sınıflandırma",
      "Kaynak olarak kullanılacak pasajların işaretlenmesi",
      "Erişim kapsamının belirlenmesi",
    ],
  },
];

export function findNavItem(pathname: string): NavItem | undefined {
  return navItems.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
}
