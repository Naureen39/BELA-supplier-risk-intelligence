"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChartCard } from "@/components/app/chart-card";
import { PageHeader, Panel } from "@/components/app/ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { dateShort, saveCsv } from "@/lib/app/format";
import { errText } from "@/lib/app/hooks";
import { useUi } from "@/lib/app/store";
import type { EventRow, Page } from "@/lib/app/types";

interface GNode {
  id: number;
  name: string;
  hop: number;
  in_portfolio: boolean;
}
interface GEdge {
  parent_id: number;
  child_id: number;
  source: string;
  as_of: string | null;
}
interface Graph {
  nodes: GNode[];
  edges: GEdge[];
  truncated: boolean;
}
interface Company {
  id: number;
  canonical_name: string;
  hq_state: string | null;
}
interface Cy {
  destroy: () => void;
  png: (o: object) => string;
  layout: (o: object) => { run: () => void };
  getElementById: (id: string) => { select: () => void; nonempty: () => boolean };
  elements: () => { removeClass: (c: string) => void };
  $: (s: string) => { addClass: (c: string) => void };
  on: (
    e: string,
    s: string,
    f: (ev: { target: { id: () => string; data: (k?: string) => unknown } }) => void,
  ) => void;
  resize: () => void;
}

function Explorer() {
  const params = useSearchParams();
  const toast = useUi((s) => s.toast);
  const theme = useUi((s) => s.theme);
  const host = useRef<HTMLDivElement>(null);
  const cy = useRef<Cy | null>(null);
  const [nodes, setNodes] = useState<
    Map<string, { label: string; kind: "company" | "supplier" | "event"; extra?: string }>
  >(new Map());
  const [edges, setEdges] = useState<
    Map<string, { s: string; t: string; source: string; as_of: string | null }>
  >(new Map());
  const [selected, setSelected] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [depth, setDepth] = useState("2");
  const [src, setSrc] = useState("");
  const [pathQ, setPathQ] = useState("");
  const [notice, setNotice] = useState("");

  const search = useQuery({
    queryKey: ["co-search", q],
    enabled: q.trim().length >= 2,
    queryFn: () =>
      api<{ items: Company[] }>(`/companies/search?q=${encodeURIComponent(q)}&limit=8`),
  });
  const pathSearch = useQuery({
    queryKey: ["co-search", pathQ],
    enabled: pathQ.trim().length >= 2,
    queryFn: () =>
      api<{ items: Company[] }>(`/companies/search?q=${encodeURIComponent(pathQ)}&limit=6`),
  });

  const merge = useCallback((g: Graph) => {
    setNodes((p) => {
      const n = new Map(p);
      for (const x of g.nodes)
        n.set(`c${x.id}`, { label: x.name, kind: x.in_portfolio ? "supplier" : "company" });
      return n;
    });
    setEdges((p) => {
      const n = new Map(p);
      for (const e of g.edges)
        n.set(`e${e.parent_id}-${e.child_id}`, {
          s: `c${e.parent_id}`,
          t: `c${e.child_id}`,
          source: e.source,
          as_of: e.as_of,
        });
      return n;
    });
    setNotice(g.truncated ? "The graph was cut at 500 nodes. Narrow the depth." : "");
  }, []);

  const load = useCallback(
    async (id: number, d: number, reset = false) => {
      try {
        const g = await api<Graph>(`/graph/neighbors?company_id=${id}&depth=${d}`);
        if (reset) {
          setNodes(new Map());
          setEdges(new Map());
        }
        merge(g);
        setSelected(`c${id}`);
      } catch (e) {
        toast("error", errText(e));
      }
    },
    [merge, toast],
  );

  useEffect(() => {
    const c = params.get("company");
    if (c) void Promise.resolve().then(() => load(Number(c), 2, true));
  }, [params, load]);

  const visibleEdges = useMemo(
    () => [...edges.entries()].filter(([, e]) => !src || e.source === src),
    [edges, src],
  );
  const sources = useMemo(() => [...new Set([...edges.values()].map((e) => e.source))], [edges]);

  useEffect(() => {
    if (!host.current || nodes.size === 0) return;
    let dead = false;
    Promise.all([import("cytoscape"), import("cytoscape-fcose")]).then(([cs, fc]) => {
      if (dead || !host.current) return;
      const cytoscape = cs.default as unknown as { (o: object): Cy; use: (x: unknown) => void };
      try {
        cytoscape.use(fc.default);
      } catch {
        /* already registered */
      }
      cy.current?.destroy();
      const dark = theme === "dark";
      const inst = cytoscape({
        container: host.current,
        elements: [
          ...[...nodes.entries()].map(([id, n]) => ({
            data: { id, label: n.label, kind: n.kind },
          })),
          ...visibleEdges
            .filter(([, e]) => nodes.has(e.s) && nodes.has(e.t))
            .map(([id, e]) => ({ data: { id, source: e.s, target: e.t, provenance: e.source } })),
        ],
        layout: {
          name: "fcose",
          animate: false,
          nodeRepulsion: 9000,
          idealEdgeLength: 90,
          padding: 40,
        },
        minZoom: 0.3,
        maxZoom: 1.1,
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "font-size": 10,
              color: dark ? "#c8d2e4" : "#334155",
              "text-valign": "bottom",
              "text-margin-y": 4,
              "background-color": "#2f74d8",
              width: 22,
              height: 22,
              "text-wrap": "ellipsis",
              "text-max-width": "110px",
            },
          },
          {
            selector: "node[kind='supplier']",
            style: {
              "background-color": "#00a3a3",
              shape: "round-rectangle",
              width: 28,
              height: 22,
            },
          },
          {
            selector: "node[kind='event']",
            style: { "background-color": "#e69f00", shape: "diamond" },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "#94a3b8",
              "target-arrow-color": "#94a3b8",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
            },
          },
          {
            selector: ".path",
            style: {
              "line-color": "#d55e5e",
              "target-arrow-color": "#d55e5e",
              "background-color": "#d55e5e",
              width: 3,
            },
          },
          { selector: ":selected", style: { "border-width": 3, "border-color": "#8e5bd9" } },
        ],
      });
      inst.on("tap", "node", (ev) => setSelected(ev.target.id()));
      cy.current = inst;
      if (selected) inst.getElementById(selected).select();
    });
    return () => {
      dead = true;
      cy.current?.destroy();
      cy.current = null;
    };
    // The graph is rebuilt when its data or theme changes, not when the selection changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, visibleEdges, theme]);

  const sel = selected ? nodes.get(selected) : undefined;
  const selId = selected?.startsWith("c") ? Number(selected.slice(1)) : null;
  const events = useQuery({
    queryKey: ["events-for", selId],
    enabled: false,
    queryFn: () => api<Page<EventRow>>(`/events?company_id=${selId}&limit=5`),
  });

  async function showEvents() {
    if (!selId) return;
    const r = await events.refetch();
    const items = r.data?.items ?? [];
    setNodes((p) => {
      const n = new Map(p);
      for (const e of items)
        n.set(`v${e.id}`, {
          label: e.title.slice(0, 40),
          kind: "event",
          extra: dateShort(e.reported_at),
        });
      return n;
    });
    setEdges((p) => {
      const n = new Map(p);
      for (const e of items)
        n.set(`ev${e.id}`, {
          s: `c${selId}`,
          t: `v${e.id}`,
          source: e.source,
          as_of: e.reported_at,
        });
      return n;
    });
  }

  async function findPath(to: number) {
    if (!selId) return toast("info", "Select a company in the graph first.");
    try {
      const r = await api<{ found: boolean; path: { id: number; name: string }[] }>(
        `/graph/path?source=${selId}&target=${to}`,
      );
      if (!r.found) return toast("info", "No ownership path connects these companies.");
      setNodes((p) => {
        const n = new Map(p);
        for (const x of r.path)
          if (!n.has(`c${x.id}`)) n.set(`c${x.id}`, { label: x.name, kind: "company" });
        return n;
      });
      setEdges((p) => {
        const n = new Map(p);
        r.path.slice(1).forEach((x, i) => {
          const a = r.path[i]!.id;
          const k = [`e${a}-${x.id}`, `e${x.id}-${a}`].find((kk) => n.has(kk));
          if (!k)
            n.set(`e${x.id}-${a}`, { s: `c${x.id}`, t: `c${a}`, source: "path", as_of: null });
        });
        return n;
      });
      setTimeout(() => {
        cy.current?.elements().removeClass("path");
        r.path.forEach((x) => cy.current?.$(`#c${x.id}`).addClass("path"));
      }, 400);
      toast("success", `Path found through ${r.path.length} companies.`);
    } catch (e) {
      toast("error", errText(e));
    }
  }

  const conc = useQuery({
    queryKey: ["concentration"],
    queryFn: () =>
      api<{
        total_suppliers: number;
        groups: {
          name: string;
          suppliers: number;
          share_of_suppliers: number;
          share_of_high_risk: number;
          cumulative_share: number;
        }[];
      }>("/graph/concentration?top=10"),
  });

  const graphTab = (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div>
        <div
          role="img"
          aria-label="Corporate graph. The same data is listed in the table below."
          ref={host}
          className="border-line h-[460px] rounded-[12px] border bg-white"
        />
        {nodes.size === 0 && (
          <p className="mt-3 text-sm text-slate-600">
            Search for a company to draw its ownership graph.
          </p>
        )}
        {notice && (
          <p role="status" className="text-warning mt-2 text-sm">
            {notice}
          </p>
        )}
        <ul className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600" aria-label="Legend">
          <li>
            <span className="bg-chart-1 mr-1 inline-block size-3 rounded-full align-middle" />
            Company
          </li>
          <li>
            <span className="bg-chart-2 mr-1 inline-block h-3 w-4 rounded-sm align-middle" />
            Supplier in your portfolio
          </li>
          <li>
            <span className="bg-chart-3 mr-1 inline-block size-3 rotate-45 align-middle" />
            Event
          </li>
          <li>
            <span className="mr-1 inline-block h-0.5 w-4 bg-slate-400 align-middle" />
            Ownership (arrow points to the subsidiary)
          </li>
          <li>
            <span className="bg-chart-5 mr-1 inline-block h-1 w-4 align-middle" />
            Shortest path
          </li>
        </ul>
      </div>
      <aside className="space-y-4" aria-label="Details">
        <Panel title="Selected">
          {sel ? (
            <div className="space-y-2 text-sm">
              <p className="text-ink font-medium">{sel.label}</p>
              <Badge tone={sel.kind === "supplier" ? "success" : "neutral"}>
                {sel.kind === "supplier" ? "In your portfolio" : sel.kind}
              </Badge>
              {sel.extra && <p className="text-slate-600">Reported {sel.extra}</p>}
              {selId && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="secondary" onClick={() => void load(selId, 1)}>
                    Expand neighbors
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => void showEvents()}>
                    Show events
                  </Button>
                </div>
              )}
              <ul className="text-xs text-slate-600">
                {[...edges.values()]
                  .filter((e) => e.s === selected || e.t === selected)
                  .map((e, i) => (
                    <li key={i}>
                      {nodes.get(e.s)?.label} to {nodes.get(e.t)?.label}: source {e.source}
                      {e.as_of ? `, as of ${dateShort(e.as_of)}` : ""}
                    </li>
                  ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-slate-600">Select a node to see its provenance.</p>
          )}
        </Panel>
        <Panel title="Shortest path">
          <label htmlFor="path-q" className="text-ink mb-1 block text-sm">
            From the selected company to
          </label>
          <Input
            id="path-q"
            value={pathQ}
            onChange={(e) => setPathQ(e.target.value)}
            placeholder="Company name"
          />
          <ul className="mt-2 space-y-1">
            {pathSearch.data?.items.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className="text-link text-left text-sm underline underline-offset-2"
                  onClick={() => void findPath(c.id)}
                >
                  {c.canonical_name}
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Export">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={nodes.size === 0}
              onClick={() => {
                const u = cy.current?.png({
                  full: true,
                  scale: 2,
                  bg: theme === "dark" ? "#152038" : "#ffffff",
                });
                if (!u) return;
                const a = document.createElement("a");
                a.href = u;
                a.download = "graph.png";
                a.click();
              }}
            >
              PNG
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={nodes.size === 0}
              onClick={() =>
                saveCsv(
                  "graph-edges.csv",
                  [...edges.values()].map((e) => ({
                    parent: nodes.get(e.s)?.label,
                    child: nodes.get(e.t)?.label,
                    source: e.source,
                    as_of: e.as_of,
                  })),
                )
              }
            >
              Edges CSV
            </Button>
          </div>
        </Panel>
      </aside>
    </div>
  );

  const g = conc.data?.groups ?? [];
  const concTab = (
    <ChartCard
      title="Concentration by ultimate parent"
      subtitle="Share of your suppliers under each parent, with the cumulative share"
      loading={conc.isLoading}
      error={conc.error}
      empty={!g.length}
      filename="concentration"
      table={{
        columns: ["Parent", "Suppliers", "Share of suppliers", "Share of high risk", "Cumulative"],
        rows: g.map((x) => ({
          Parent: x.name,
          Suppliers: x.suppliers,
          "Share of suppliers": `${(x.share_of_suppliers * 100).toFixed(1)}%`,
          "Share of high risk": `${(x.share_of_high_risk * 100).toFixed(1)}%`,
          Cumulative: `${(x.cumulative_share * 100).toFixed(1)}%`,
        })),
      }}
      option={{
        tooltip: { trigger: "axis" },
        legend: { bottom: 0, textStyle: { color: "#64748b" } },
        grid: { left: 56, right: 56, top: 16, bottom: 90 },
        xAxis: {
          type: "category",
          data: g.map((x) => x.name),
          axisLabel: { rotate: 25, interval: 0, width: 90, overflow: "truncate" },
        },
        yAxis: [
          {
            type: "value",
            name: "Share (%)",
            nameLocation: "middle",
            nameGap: 40,
            max: 100,
            splitLine: { lineStyle: { color: "#94a3b833" } },
          },
          { type: "value", max: 100, name: "Cumulative (%)", nameLocation: "middle", nameGap: 40 },
        ],
        series: [
          {
            name: "Share of suppliers",
            type: "bar",
            data: g.map((x) => +(x.share_of_suppliers * 100).toFixed(1)),
          },
          {
            name: "Share of high-risk suppliers",
            type: "bar",
            data: g.map((x) => +(x.share_of_high_risk * 100).toFixed(1)),
          },
          {
            name: "Cumulative share",
            type: "line",
            yAxisIndex: 1,
            data: g.map((x) => +(x.cumulative_share * 100).toFixed(1)),
          },
        ],
      }}
      height={340}
    />
  );

  return (
    <>
      <PageHeader
        title="Corporate explorer"
        text="Follow ownership from a company to its parents and subsidiaries. Every edge shows its source and as-of date."
      />
      <div className="border-line mb-4 grid gap-3 rounded-[12px] border bg-white p-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
        <div>
          <label htmlFor="co-q" className="mb-1 block text-xs font-medium text-slate-600">
            Search a company
          </label>
          <Input
            id="co-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Company name or ticker"
            autoComplete="off"
          />
          {search.data?.items.length ? (
            <ul className="border-line mt-1 rounded-[8px] border">
              {search.data.items.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => {
                      void load(c.id, Number(depth), true);
                      setQ("");
                    }}
                    className="text-ink block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50"
                  >
                    {c.canonical_name}
                    {c.hq_state ? ` (${c.hq_state})` : ""}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div>
          <label htmlFor="depth" className="mb-1 block text-xs font-medium text-slate-600">
            Depth
          </label>
          <Select
            id="depth"
            value={depth}
            onChange={(e) => setDepth(e.target.value)}
            className="h-11 w-24"
          >
            {[1, 2, 3].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="src" className="mb-1 block text-xs font-medium text-slate-600">
            Edge source
          </label>
          <Select
            id="src"
            value={src}
            onChange={(e) => setSrc(e.target.value)}
            className="h-11 w-36"
          >
            <option value="">All</option>
            {sources.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </div>
        <Button
          variant="ghost"
          onClick={() => {
            setNodes(new Map());
            setEdges(new Map());
            setSelected(null);
          }}
        >
          Clear
        </Button>
      </div>
      <Tabs
        label="Explorer views"
        items={[
          { id: "graph", label: "Graph", content: graphTab },
          { id: "conc", label: "Concentration", content: concTab },
        ]}
      />
    </>
  );
}

export default function ExplorerPage() {
  return (
    <Suspense>
      <Explorer />
    </Suspense>
  );
}
