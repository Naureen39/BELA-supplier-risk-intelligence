"use client";

import * as DM from "@radix-ui/react-dropdown-menu";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  Activity,
  Bell,
  Building2,
  Check,
  ChevronDown,
  CreditCard,
  Database,
  DollarSign,
  FileText,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  PieChart,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { Wordmark } from "@/components/art/logo";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { ago } from "@/lib/app/format";
import { can, NAV, useMe, type Me } from "@/lib/app/session";
import { useUi, loadTheme } from "@/lib/app/store";
import { Toaster } from "./ui";

const ICONS: Record<string, typeof Bell> = {
  layout: LayoutDashboard,
  building: Building2,
  bell: Bell,
  activity: Activity,
  network: Network,
  check: Check,
  chart: PieChart,
  file: FileText,
  database: Database,
  card: CreditCard,
  shield: ShieldCheck,
  dollar: DollarSign,
  settings: Settings,
};
const IDLE_MS = 30 * 60 * 1000;

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-md py-24 text-center">
        <h1 className="text-xl font-semibold">Something went wrong on this page</h1>
        <p className="mt-2 text-slate-600">The rest of the application is unaffected.</p>
        <Button className="mt-4" onClick={() => this.setState({ failed: false })}>
          Try again
        </Button>
      </div>
    );
  }
}

interface LiveAlert {
  id?: string;
  supplier_name?: string;
  kind?: string;
  detail?: string;
  at: string;
}

function useLiveAlerts(enabled: boolean) {
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [items, setItems] = useState<LiveAlert[]>([]);
  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource("/api/v1/stream/alerts");
    es.addEventListener("alert", (e) => {
      try {
        const d = JSON.parse((e as MessageEvent).data) as LiveAlert;
        setItems((p) => [{ ...d, at: new Date().toISOString() }, ...p].slice(0, 20));
        toast("info", `New alert${d.supplier_name ? `: ${d.supplier_name}` : ""}`);
        void qc.invalidateQueries({ queryKey: ["alerts"] });
        void qc.invalidateQueries({ queryKey: ["overview"] });
      } catch {
        /* ignore a malformed message */
      }
    });
    return () => es.close();
  }, [enabled, qc, toast]);
  return items;
}

function Palette() {
  const open = useUi((s) => s.paletteOpen);
  const setOpen = useUi((s) => s.setPalette);
  const router = useRouter();
  const [q, setQ] = useState("");
  const me = useMe().data;
  const results = useQuery({
    queryKey: ["palette", q],
    enabled: open && q.trim().length >= 2,
    queryFn: async () => {
      const [s, c] = await Promise.all([
        api<{ items: { id: string; uploaded_name: string; company_name: string | null }[] }>(
          `/suppliers?q=${encodeURIComponent(q)}&limit=6`,
        ).catch(() => ({ items: [] })),
        api<{ items: { id: number; canonical_name: string }[] }>(
          `/companies/search?q=${encodeURIComponent(q)}&limit=6`,
        ).catch(() => ({ items: [] })),
      ]);
      return { suppliers: s.items, companies: c.items };
    },
  });
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUi.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [setOpen]);
  if (!open) return null;
  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };
  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="border-line w-full max-w-xl overflow-hidden rounded-[12px] border bg-white shadow-[var(--shadow-3)]"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      >
        <Command shouldFilter={false}>
          <Command.Input
            autoFocus
            value={q}
            onValueChange={setQ}
            placeholder="Search suppliers, companies, and pages"
            aria-label="Search suppliers, companies, and pages"
            className="border-line text-ink w-full border-b bg-transparent px-4 py-3 text-[15px] outline-none placeholder:text-slate-500"
          />
          <Command.List className="max-h-80 overflow-auto p-2">
            <Command.Empty className="px-3 py-6 text-center text-sm text-slate-600">
              {q.length < 2
                ? "Type at least two characters."
                : results.isFetching
                  ? "Searching"
                  : "No results."}
            </Command.Empty>
            {results.data?.suppliers.length ? (
              <Command.Group heading="Suppliers" className="text-xs text-slate-600">
                {results.data.suppliers.map((s) => (
                  <Command.Item
                    key={s.id}
                    value={`s-${s.id}`}
                    onSelect={() => go(`/app/suppliers/${s.id}`)}
                    className="text-ink cursor-pointer rounded-[8px] px-3 py-2 text-sm aria-selected:bg-slate-100"
                  >
                    {s.uploaded_name}
                    {s.company_name && <span className="text-slate-600"> ({s.company_name})</span>}
                  </Command.Item>
                ))}
              </Command.Group>
            ) : null}
            {results.data?.companies.length ? (
              <Command.Group heading="Companies" className="text-xs text-slate-600">
                {results.data.companies.map((c) => (
                  <Command.Item
                    key={c.id}
                    value={`c-${c.id}`}
                    onSelect={() => go(`/app/explorer?company=${c.id}`)}
                    className="text-ink cursor-pointer rounded-[8px] px-3 py-2 text-sm aria-selected:bg-slate-100"
                  >
                    {c.canonical_name}
                  </Command.Item>
                ))}
              </Command.Group>
            ) : null}
            <Command.Group heading="Pages" className="text-xs text-slate-600">
              {NAV.filter((n) => can(me, n.permission)).map((n) => (
                <Command.Item
                  key={n.href}
                  value={`p-${n.href}`}
                  onSelect={() => go(n.href)}
                  className="text-ink cursor-pointer rounded-[8px] px-3 py-2 text-sm aria-selected:bg-slate-100"
                >
                  {n.label}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}

function Sidebar({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const path = usePathname();
  const groups = useMemo(() => {
    const visible = NAV.filter((n) => can(me, n.permission));
    return (["Monitor", "Investigate", "Manage", "Platform"] as const)
      .map((g) => ({ g, items: visible.filter((n) => n.group === g) }))
      .filter((x) => x.items.length);
  }, [me]);
  return (
    <nav aria-label="Application" className="flex flex-col gap-5 p-3">
      {groups.map(({ g, items }) => (
        <div key={g}>
          <p className="mb-1 px-2 text-xs font-semibold tracking-wider text-slate-600 uppercase">
            {g}
          </p>
          <ul className="space-y-0.5">
            {items.map((n) => {
              const Icon = ICONS[n.icon] ?? LayoutDashboard;
              const active = n.href === "/app" ? path === "/app" : path.startsWith(n.href);
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-sm font-medium ${active ? "bg-brand-100 text-link" : "text-slate-700 hover:bg-slate-100"}`}
                  >
                    <Icon className="size-4.5" aria-hidden />
                    {n.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const qc = useQueryClient();
  const meQ = useMe();
  const me = meQ.data;
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const setPalette = useUi((s) => s.setPalette);
  const [drawer, setDrawer] = useState(false);
  const live = useLiveAlerts(!!me && can(me, "view") && !!me.tenant_id);
  const idle = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(loadTheme, []);
  useEffect(() => {
    if (meQ.isError) router.replace("/login");
  }, [meQ.isError, router]);

  const signOut = async (reason?: string) => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    router.replace(reason ? `/login?reason=${reason}` : "/login");
  };

  useEffect(() => {
    if (!me) return;
    const reset = () => {
      clearTimeout(idle.current);
      idle.current = setTimeout(() => void signOut("idle"), IDLE_MS);
    };
    const events = ["pointerdown", "keydown", "scroll"] as const;
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      events.forEach((e) => window.removeEventListener(e, reset));
      clearTimeout(idle.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);

  if (!me) {
    return (
      <div className={theme === "dark" ? "app-dark" : "app-light"}>
        <div
          className="grid min-h-screen place-items-center"
          role="status"
          aria-label="Loading the application"
        >
          <Wordmark />
        </div>
      </div>
    );
  }

  return (
    <div className={`${theme === "dark" ? "app-dark" : "app-light"} min-h-screen`}>
      <a
        href="#app-main"
        className="focus:text-ink sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[80] focus:rounded-[8px] focus:bg-white focus:px-4 focus:py-2"
      >
        Skip to main content
      </a>
      <div className="lg:grid lg:grid-cols-[232px_1fr]">
        <aside className="border-line sticky top-0 hidden h-screen overflow-y-auto border-r bg-white lg:block">
          <div className="p-4">
            <Link href="/app" aria-label="Provenance Risk, application home">
              <Wordmark />
            </Link>
          </div>
          <Sidebar me={me} />
        </aside>
        <div className="min-w-0">
          <header className="border-line sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-white/90 px-4 backdrop-blur">
            <button
              type="button"
              className="rounded-[8px] p-2 hover:bg-slate-100 lg:hidden"
              aria-label="Open navigation"
              onClick={() => setDrawer(true)}
            >
              <Menu className="size-5" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => setPalette(true)}
              className="flex h-9 w-full max-w-sm items-center gap-2 rounded-[8px] border border-slate-300 bg-white px-3 text-left text-sm text-slate-600 hover:bg-slate-50"
            >
              <Search className="size-4" aria-hidden />
              <span className="flex-1 truncate">Search</span>
              <kbd className="hidden rounded border border-slate-300 px-1.5 text-xs sm:inline">
                Ctrl K
              </kbd>
            </button>
            <div className="ml-auto flex items-center gap-1">
              <TenantName />
              <DM.Root>
                <DM.Trigger asChild>
                  <button
                    type="button"
                    className="relative rounded-[8px] p-2 hover:bg-slate-100"
                    aria-label={`Notifications, ${live.length} new`}
                  >
                    <Bell className="size-5" aria-hidden />
                    {live.length > 0 && (
                      <span
                        className="bg-danger absolute top-1 right-1 size-2.5 rounded-full"
                        aria-hidden
                      />
                    )}
                  </button>
                </DM.Trigger>
                <DM.Portal>
                  <DM.Content
                    align="end"
                    className="border-line z-50 w-80 rounded-[10px] border bg-white p-2 shadow-[var(--shadow-3)]"
                  >
                    <p className="px-2 py-1 text-xs font-semibold text-slate-600 uppercase">
                      Live alerts
                    </p>
                    {live.length === 0 ? (
                      <p className="px-2 py-4 text-sm text-slate-600">
                        New alerts appear here as they arrive.
                      </p>
                    ) : (
                      live.map((a, i) => (
                        <DM.Item
                          key={i}
                          onSelect={() => router.push("/app/alerts")}
                          className="text-ink cursor-pointer rounded-[8px] px-2 py-2 text-sm outline-none data-[highlighted]:bg-slate-100"
                        >
                          <span className="block font-medium">{a.supplier_name ?? "Alert"}</span>
                          <span className="block text-xs text-slate-600">
                            {a.detail ?? a.kind} &middot; {ago(a.at)}
                          </span>
                        </DM.Item>
                      ))
                    )}
                  </DM.Content>
                </DM.Portal>
              </DM.Root>
              <button
                type="button"
                className="rounded-[8px] p-2 hover:bg-slate-100"
                aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? (
                  <Sun className="size-5" aria-hidden />
                ) : (
                  <Moon className="size-5" aria-hidden />
                )}
              </button>
              <DM.Root>
                <DM.Trigger asChild>
                  <button
                    type="button"
                    className="flex items-center gap-1.5 rounded-[8px] p-1.5 pl-2 text-sm hover:bg-slate-100"
                    aria-label="User menu"
                  >
                    <span className="bg-brand-100 text-link grid size-7 place-items-center rounded-full text-xs font-semibold">
                      {me.email[0]?.toUpperCase()}
                    </span>
                    <ChevronDown className="size-4" aria-hidden />
                  </button>
                </DM.Trigger>
                <DM.Portal>
                  <DM.Content
                    align="end"
                    className="border-line z-50 w-60 rounded-[10px] border bg-white p-1 shadow-[var(--shadow-3)]"
                  >
                    <div className="px-3 py-2">
                      <p className="text-ink truncate text-sm font-medium">{me.email}</p>
                      <p className="text-xs text-slate-600">{me.role.replace("_", " ")}</p>
                    </div>
                    <DM.Separator className="bg-line my-1 h-px" />
                    <DM.Item
                      onSelect={() => router.push("/app/settings")}
                      className="text-ink cursor-pointer rounded-[8px] px-3 py-2 text-sm outline-none data-[highlighted]:bg-slate-100"
                    >
                      Settings
                    </DM.Item>
                    <DM.Item
                      onSelect={() => void signOut()}
                      className="text-ink cursor-pointer rounded-[8px] px-3 py-2 text-sm outline-none data-[highlighted]:bg-slate-100"
                    >
                      Sign out
                    </DM.Item>
                  </DM.Content>
                </DM.Portal>
              </DM.Root>
            </div>
          </header>
          <main id="app-main" className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6">
            <Boundary>{children}</Boundary>
          </main>
        </div>
      </div>
      {drawer && (
        <div
          className="fixed inset-0 z-50 lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          <div className="absolute inset-0 bg-black/50" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-72 overflow-y-auto bg-white">
            <div className="flex items-center justify-between p-4">
              <Wordmark />
              <button
                type="button"
                aria-label="Close navigation"
                onClick={() => setDrawer(false)}
                className="rounded p-1 hover:bg-slate-100"
              >
                <X className="size-5" aria-hidden />
              </button>
            </div>
            <Sidebar me={me} onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <Palette />
      <Toaster />
    </div>
  );
}

function TenantName() {
  const t = useQuery({
    queryKey: ["tenant"],
    queryFn: () => api<{ name: string }>("/tenants/current"),
    retry: false,
  });
  return t.data ? (
    <span className="mr-2 hidden max-w-48 truncate text-sm text-slate-600 md:inline">
      {t.data.name}
    </span>
  ) : null;
}
