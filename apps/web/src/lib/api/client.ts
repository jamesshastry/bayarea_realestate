/**
 * Typed fetch wrapper around the FastAPI backend.
 *
 * Phase 2 scaffold: `apps/web/src/api/generated/` is the codegen target —
 * once `apps/api/openapi.json` is committed and the codegen script runs
 * (Phase 2 deliverable), the typed client will be a generated mirror of the
 * server's response models. Until then, callers pass response types
 * inline (see `apps/web/src/app/status/page.tsx`).
 *
 * Conventions:
 * - Bases URL from `NEXT_PUBLIC_API_BASE_URL` (set per-env on Vercel).
 * - In dev, defaults to `http://localhost:8000`.
 * - 5xx responses throw; 4xx surface as typed `ApiError`s so pages can render
 *   informative empty states.
 */

const DEFAULT_BASE_URL = "http://localhost:8000";

const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_BASE_URL;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOpts {
  /** Forwarded to fetch — used for ISR via `next: { revalidate: 60 }`. */
  next?: { revalidate?: number; tags?: string[] };
  /** Override default cache mode. */
  cache?: RequestCache;
  /** Extra headers (auth, etc.). */
  headers?: HeadersInit;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  opts: RequestOpts = {},
): Promise<T> {
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;

  const init: RequestInit & { next?: RequestOpts["next"] } = {
    method,
    headers: {
      "content-type": "application/json",
      accept: "application/json",
      ...(opts.headers ?? {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    ...(opts.cache ? { cache: opts.cache } : {}),
    ...(opts.next ? { next: opts.next } : {}),
  };

  const resp = await fetch(url, init);
  const text = await resp.text();
  const parsed = text ? safeJsonParse(text) : undefined;

  if (!resp.ok) {
    throw new ApiError(
      `API ${method} ${path} → ${resp.status}`,
      resp.status,
      parsed ?? text,
    );
  }
  return parsed as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const apiClient = {
  get: <T>(path: string, opts?: RequestOpts) =>
    request<T>("GET", path, undefined, opts),
  post: <T>(path: string, body: unknown, opts?: RequestOpts) =>
    request<T>("POST", path, body, opts),
  put: <T>(path: string, body: unknown, opts?: RequestOpts) =>
    request<T>("PUT", path, body, opts),
  delete: <T>(path: string, opts?: RequestOpts) =>
    request<T>("DELETE", path, undefined, opts),
};
