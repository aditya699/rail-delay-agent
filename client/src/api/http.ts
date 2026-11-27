// A thin fetch wrapper: base URL, JSON handling and typed errors.

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Error thrown for any non-2xx response, carrying the server's error code. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string };
  detail?: unknown;
}

function describe(body: ErrorBody | null, fallback: string): { code: string; message: string } {
  if (body?.error?.message) {
    return { code: body.error.code ?? "error", message: body.error.message };
  }
  // FastAPI validation errors: { detail: [{ msg, loc }] }
  if (Array.isArray(body?.detail)) {
    const first = body.detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    if (first?.msg) {
      return { code: "validation_error", message: `${first.loc?.slice(-1)[0] ?? "input"}: ${first.msg}` };
    }
  }
  if (typeof body?.detail === "string") {
    return { code: "error", message: body.detail };
  }
  return { code: "error", message: fallback };
}

/** Make a request and parse JSON. `body` may be a plain object (sent as JSON) or FormData. */
export async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = "GET", body, signal } = options;
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      signal,
      headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is the server running?`, 0, "network");
  }

  if (!response.ok) {
    const parsed = (await response.json().catch(() => null)) as ErrorBody | null;
    const { code, message } = describe(parsed, `${response.status} ${response.statusText}`);
    throw new ApiError(message, response.status, code);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** True when `error` is the API saying a request clashes with current state (HTTP 409). */
export function isConflict(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 409;
}
