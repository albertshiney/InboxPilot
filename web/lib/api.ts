// Thin, typed fetch helpers for client components. Every call goes through
// `/api/backend/<path>` — the session-validating proxy in
// `app/api/backend/[...path]/route.ts` — which is the only path from the
// browser to the FastAPI backend. `path` should omit the leading slash,
// e.g. `apiGet<Thread[]>("threads")`.

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data: unknown = await res.clone().json();
    if (data && typeof data === "object") {
      const record = data as Record<string, unknown>;
      if (typeof record.message === "string") return record.message;
      if (typeof record.detail === "string") return record.detail;
    }
    return JSON.stringify(data);
  } catch {
    try {
      const text = await res.text();
      if (text) return text;
    } catch {
      // fall through to statusText below
    }
    return res.statusText || `Request failed with status ${res.status}`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/backend/${path}`, init);

  if (!res.ok) {
    throw new Error(await extractErrorMessage(res));
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// For multipart/form-data uploads. Do not set a Content-Type header here —
// the browser must generate one with the correct multipart boundary.
export function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: formData,
  });
}
