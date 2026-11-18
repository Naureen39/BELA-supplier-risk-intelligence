import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiRequestError } from "@/lib/api";
import { useUi } from "./store";
import type { Page } from "./types";

/** Cursor-paginated list. `path` already contains its filters. */
export function useCursorList<T>(key: unknown[], path: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: key,
    enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const sep = path.includes("?") ? "&" : "?";
      return api<Page<T>>(
        `${path}${pageParam ? `${sep}cursor=${encodeURIComponent(pageParam)}` : ""}`,
      );
    },
    getNextPageParam: (last) => last.next_cursor,
  });
}

export const flat = <T>(data: { pages: Page<T>[] } | undefined): T[] =>
  data?.pages.flatMap((p) => p.items) ?? [];

export function errText(e: unknown): string {
  if (e instanceof ApiRequestError)
    return e.problem.detail ?? e.problem.title ?? `Request failed (${e.status})`;
  return e instanceof Error ? e.message : "The request failed.";
}

/** Mutation that reports success and failure as toasts and refreshes the given query keys. */
export function useAction<V, R = unknown>(
  fn: (v: V) => Promise<R>,
  opts: { success?: string; invalidate?: string[][]; onDone?: (r: R) => void } = {},
) {
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      if (opts.success) toast("success", opts.success);
      opts.invalidate?.forEach((k) => void qc.invalidateQueries({ queryKey: k }));
      opts.onDone?.(r);
    },
    onError: (e) => toast("error", errText(e)),
  });
}

export const qs = (
  params: Record<string, string | number | boolean | null | undefined>,
): string => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params))
    if (v !== null && v !== undefined && v !== "" && v !== false) u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
};
