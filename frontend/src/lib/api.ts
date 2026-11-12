import type { Health, POView, RunCreated, RunDetail, RunFilters, RunList, Stats, Vendor } from "./types";

function query(params: object): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Fired after any change a reviewer makes, so independent widgets can refresh. */
export const DATA_CHANGED = "ap:data-changed";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail: unknown }).detail;
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  runs: (filters: RunFilters = {}) => request<RunList>(`/api/runs${query({ limit: 500, ...filters })}`),
  stats: () => request<Stats>("/api/stats"),
  pos: () => request<POView[]>("/api/pos"),
  vendors: () => request<Vendor[]>("/api/vendors"),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<RunCreated>("/api/runs", { method: "POST", body });
  },
  review: async (id: string, action: "APPROVE" | "REJECT", note: string) => {
    const run = await request<RunDetail>(`/api/runs/${encodeURIComponent(id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    });
    window.dispatchEvent(new Event(DATA_CHANGED)); // lets the top bar badge update at once
    return run;
  },
  fileUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/file`,
  eventsUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/events`,
};
