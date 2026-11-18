/** Same-origin API client. The web server proxies /api to the backend (see next.config.mjs). */

export interface Problem {
  title?: string;
  detail?: string;
  code?: string;
  status?: number;
}

export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public problem: Problem,
  ) {
    super(problem.detail ?? problem.title ?? `Request failed (${status})`);
  }
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith("pr_csrf="))
    ?.split("=")[1];
}

let refreshing: Promise<boolean> | null = null;

/** Renew the session once for all concurrent callers. Returns false when the session is gone. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken() ?? "" },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

const NO_REFRESH = ["/auth/login", "/auth/refresh", "/auth/mfa", "/auth/password"];

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const res = await send(path, init);
  if (
    res.status === 401 &&
    !NO_REFRESH.some((p) => path.startsWith(p)) &&
    (await refreshSession())
  ) {
    return parse<T>(await send(path, init));
  }
  return parse<T>(res);
}

async function send(path: string, init: RequestInit & { json?: unknown }): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? (init.json !== undefined ? "POST" : "GET")).toUpperCase();
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  const csrf = csrfToken();
  if (csrf && method !== "GET") headers.set("X-CSRF-Token", csrf);
  return fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : {};
  if (!res.ok) throw new ApiRequestError(res.status, data as Problem);
  return data as T;
}

/** Download a file endpoint (CSV or PDF) through the same authenticated path. */
export async function download(path: string, filename: string): Promise<void> {
  const res = await send(path, {});
  if (!res.ok)
    throw new ApiRequestError(res.status, (await res.json().catch(() => ({}))) as Problem);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Server-side fetch used at build and revalidation time. Returns null when the API is unreachable. */
export async function serverApi<T>(path: string, revalidate = 3600): Promise<T | null> {
  const origin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${origin}/api/v1${path}`, {
      next: { revalidate },
      signal: AbortSignal.timeout(4000),
    });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}
