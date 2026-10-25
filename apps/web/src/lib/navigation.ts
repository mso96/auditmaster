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
      "Kaydedilen denetimler ve bunlara bağlı risk kontrol matrisleri burada listelenir.",
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
      "Kapsam yazıldığında kütüphanedeki pasajlar bulunur; risk, kontrol ve test önerileri kaynaklarıyla üretilir. Kabul, düzeltme ve ret kararı denetçiye aittir.",
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
      "Kabul edilmiş kontroller için kaynaklı test adımları önerilir. Adımları inceleyin, düzenleyin ve kararlarınızı kaydedin. Hiçbir test otomatik çalıştırılmaz.",
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
      "Denetim raporları, bulgular, prosedürler, standartlar ve iyi uygulamalar burada tutulur. Metin parçalanır; RCM önerileri bu parçalara dayanır.",
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
