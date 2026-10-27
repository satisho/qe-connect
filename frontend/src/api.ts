// Small fetch wrapper: JSON in and out, the anti-forgery header on every change, readable errors.
export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (method !== "GET") headers["X-QEC"] = "1";
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Can't reach QE Connect. Check that it is still running, then try again.");
  }
  const text = await res.text();
  let data: any = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : d?.message || `Something went wrong (${res.status}).`;
    if (res.status === 401 && !url.startsWith("/api/auth/") && !url.startsWith("/api/s/")) {
      window.dispatchEvent(new CustomEvent("qec:signed-out", { detail: msg }));
    }
    throw new ApiError(res.status, msg, d);
  }
  return data as T;
}

export const api = {
  get: <T,>(url: string) => request<T>("GET", url),
  post: <T,>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T,>(url: string, body?: unknown) => request<T>("PUT", url, body ?? {}),
  patch: <T,>(url: string, body?: unknown) => request<T>("PATCH", url, body ?? {}),
  del: <T,>(url: string) => request<T>("DELETE", url),
};

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
