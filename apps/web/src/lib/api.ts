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

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? (init.json !== undefined ? "POST" : "GET")).toUpperCase();
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  const csrf = csrfToken();
  if (csrf && method !== "GET") headers.set("X-CSRF-Token", csrf);
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : {};
  if (!res.ok) throw new ApiRequestError(res.status, data as Problem);
  return data as T;
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
