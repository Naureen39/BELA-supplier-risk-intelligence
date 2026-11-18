"use client";

import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Columns3, Download, Save } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/skeleton";
import { saveCsv } from "@/lib/app/format";
import { readViews, writeViews, type SavedView } from "@/lib/app/store";
import { ErrorState, SkeletonRows } from "./ui";

export interface TableProps<T> {
  id: string;
  caption: string;
  data: T[];
  columns: ColumnDef<T, unknown>[];
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: string;
  onRowClick?: (row: T) => void;
  exportName?: string;
  /** Extra filter state to save with a view (the page owns the filters). */
  viewState?: Record<string, unknown>;
  onApplyView?: (state: Record<string, unknown>) => void;
  footer?: React.ReactNode;
  rowKey: (row: T) => string;
  toolbar?: React.ReactNode;
}

/** Sortable table with a column chooser, saved views (kept in this browser), and CSV export. */
export function DataTable<T>({
  id,
  caption,
  data,
  columns,
  loading,
  error,
  onRetry,
  empty = "Nothing to show.",
  onRowClick,
  exportName,
  viewState,
  onApplyView,
  footer,
  rowKey,
  toolbar,
}: TableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const [chooser, setChooser] = useState(false);
  const [views, setViews] = useState<SavedView[]>(() =>
    typeof window === "undefined" ? [] : readViews(id),
  );
  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnVisibility: visibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const saveView = () => {
    const name = window.prompt("Name this view");
    if (!name) return;
    const next = [
      ...views.filter((v) => v.name !== name),
      { name, state: { ...viewState, _columns: visibility, _sort: sorting } },
    ];
    setViews(next);
    writeViews(id, next);
  };
  const applyView = (name: string) => {
    const v = views.find((x) => x.name === name);
    if (!v) return;
    const { _columns, _sort, ...rest } = v.state as {
      _columns?: VisibilityState;
      _sort?: SortingState;
    } & Record<string, unknown>;
    setVisibility(_columns ?? {});
    setSorting(_sort ?? []);
    onApplyView?.(rest);
  };

  const exportCsv = () => {
    const cols = table.getVisibleLeafColumns().filter((c) => c.id !== "actions");
    saveCsv(
      `${exportName ?? id}.csv`,
      table
        .getRowModel()
        .rows.map((r) =>
          Object.fromEntries(
            cols.map((c) => [String(c.columnDef.header ?? c.id), String(r.getValue(c.id) ?? "")]),
          ),
        ),
    );
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {toolbar}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {views.length > 0 && (
            <>
              <label htmlFor={`${id}-views`} className="sr-only">
                Saved views
              </label>
              <select
                id={`${id}-views`}
                defaultValue=""
                onChange={(e) => e.target.value && applyView(e.target.value)}
                className="text-ink h-9 rounded-[8px] border border-slate-300 bg-white px-2 text-sm"
              >
                <option value="">Saved views</option>
                {views.map((v) => (
                  <option key={v.name}>{v.name}</option>
                ))}
              </select>
            </>
          )}
          <Button size="sm" variant="secondary" onClick={saveView}>
            <Save className="size-4" aria-hidden />
            Save view
          </Button>
          <div className="relative">
            <Button
              size="sm"
              variant="secondary"
              aria-expanded={chooser}
              onClick={() => setChooser(!chooser)}
            >
              <Columns3 className="size-4" aria-hidden />
              Columns
            </Button>
            {chooser && (
              <div
                role="group"
                aria-label="Choose columns"
                className="border-line absolute right-0 z-20 mt-1 w-48 rounded-[10px] border bg-white p-2 shadow-[var(--shadow-2)]"
              >
                {table
                  .getAllLeafColumns()
                  .filter((c) => c.id !== "actions")
                  .map((c) => (
                    <label
                      key={c.id}
                      className="text-ink flex items-center gap-2 px-2 py-1 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={c.getIsVisible()}
                        onChange={c.getToggleVisibilityHandler()}
                        className="accent-brand-600"
                      />
                      {String(c.columnDef.header ?? c.id)}
                    </label>
                  ))}
              </div>
            )}
          </div>
          <Button size="sm" variant="secondary" onClick={exportCsv} disabled={!data.length}>
            <Download className="size-4" aria-hidden />
            CSV
          </Button>
        </div>
      </div>
      {loading ? (
        <SkeletonRows />
      ) : error ? (
        <ErrorState error={error} retry={onRetry} />
      ) : data.length === 0 ? (
        <EmptyState title={empty} />
      ) : (
        <div
          className="border-line overflow-x-auto rounded-[12px] border bg-white"
          tabIndex={0}
          role="region"
          aria-label={`${caption}, scrolls horizontally on small screens`}
        >
          <table className="w-full min-w-[640px] text-left text-sm">
            <caption className="sr-only">{caption}</caption>
            <thead className="bg-slate-50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => {
                    const sorted = h.column.getIsSorted();
                    return (
                      <th
                        key={h.id}
                        scope="col"
                        aria-sort={
                          sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"
                        }
                        className="text-ink px-3 py-2.5 font-medium"
                      >
                        {h.column.getCanSort() ? (
                          <button
                            type="button"
                            onClick={h.column.getToggleSortingHandler()}
                            className="hover:text-link inline-flex items-center gap-1"
                          >
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {sorted === "asc" ? (
                              <ArrowUp className="size-3.5" aria-hidden />
                            ) : sorted === "desc" ? (
                              <ArrowDown className="size-3.5" aria-hidden />
                            ) : null}
                          </button>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={rowKey(row.original)}
                  className={`border-line border-t ${onRowClick ? "cursor-pointer hover:bg-slate-50" : ""}`}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2.5 align-middle text-slate-800">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {footer}
    </div>
  );
}
