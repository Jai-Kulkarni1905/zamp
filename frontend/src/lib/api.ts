import type { Health, RunCreated, RunDetail } from "./types";

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
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  upload: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<RunCreated>("/api/runs", { method: "POST", body });
  },
  review: (id: string, action: "APPROVE" | "REJECT", note: string) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(id)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    }),
  fileUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/file`,
  eventsUrl: (id: string) => `/api/runs/${encodeURIComponent(id)}/events`,
};
