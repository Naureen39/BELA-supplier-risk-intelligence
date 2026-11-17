import {
  AlertTriangle,
  Briefcase,
  Car,
  Code2,
  FileText,
  FlaskConical,
  Gauge,
  Landmark,
  Layers,
  Leaf,
  Network,
  Package,
  Radar,
  Search,
  ShieldCheck,
  Truck,
  Upload,
  Users,
  Utensils,
  Factory,
  type LucideIcon,
} from "lucide-react";
import type { IconName } from "@/lib/site";

const ICONS: Record<IconName, LucideIcon> = {
  search: Search,
  network: Network,
  alert: AlertTriangle,
  gauge: Gauge,
  radar: Radar,
  code: Code2,
  briefcase: Briefcase,
  shield: ShieldCheck,
  landmark: Landmark,
  leaf: Leaf,
  factory: Factory,
  car: Car,
  utensils: Utensils,
  package: Package,
  flask: FlaskConical,
  truck: Truck,
  upload: Upload,
  layers: Layers,
  file: FileText,
  users: Users,
};

export function Icon({ name, className }: { name: IconName; className?: string }) {
  const C = ICONS[name];
  return <C className={className} aria-hidden strokeWidth={1.75} />;
}
