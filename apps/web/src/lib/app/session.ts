import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface Me {
  id: string;
  email: string;
  role: Role;
  tenant_id: string | null;
  permissions: string[];
  mfa_enabled: boolean;
}

export type Role =
  "viewer" | "analyst" | "manager" | "tenant_admin" | "finance_analyst" | "platform_admin";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/auth/me"),
    staleTime: 60_000,
    retry: false,
  });
}

export const can = (me: Me | undefined, permission: string): boolean =>
  !!me && me.permissions.includes(permission);

export interface NavEntry {
  href: string;
  label: string;
  group: "Monitor" | "Investigate" | "Manage" | "Platform";
  permission: string;
  icon: string;
}

/** The permission names match the API's role matrix. Hiding an entry is a convenience: the API enforces access. */
export const NAV: NavEntry[] = [
  { href: "/app", label: "Overview", group: "Monitor", permission: "view", icon: "layout" },
  {
    href: "/app/suppliers",
    label: "Suppliers",
    group: "Monitor",
    permission: "view",
    icon: "building",
  },
  { href: "/app/alerts", label: "Alerts", group: "Monitor", permission: "view", icon: "bell" },
  {
    href: "/app/events",
    label: "Events",
    group: "Investigate",
    permission: "view",
    icon: "activity",
  },
  {
    href: "/app/explorer",
    label: "Explorer",
    group: "Investigate",
    permission: "view",
    icon: "network",
  },
  {
    href: "/app/reviews",
    label: "Review queue",
    group: "Investigate",
    permission: "upload_review",
    icon: "check",
  },
  {
    href: "/app/analytics",
    label: "Analytics",
    group: "Manage",
    permission: "manage_rules",
    icon: "chart",
  },
  {
    href: "/app/reports",
    label: "Reports",
    group: "Manage",
    permission: "manage_rules",
    icon: "file",
  },
  {
    href: "/app/sources",
    label: "Data sources",
    group: "Manage",
    permission: "manage_rules",
    icon: "database",
  },
  {
    href: "/app/billing",
    label: "Billing",
    group: "Manage",
    permission: "manage_users",
    icon: "card",
  },
  {
    href: "/app/admin",
    label: "Administration",
    group: "Manage",
    permission: "manage_users",
    icon: "shield",
  },
  {
    href: "/app/platform/revenue",
    label: "Revenue",
    group: "Platform",
    permission: "view_revenue",
    icon: "dollar",
  },
  {
    href: "/app/settings",
    label: "Settings",
    group: "Manage",
    permission: "view",
    icon: "settings",
  },
];
