import type { Job, JobOptions, User } from "./types";

class UnauthenticatedError extends Error {}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, { credentials: "include", ...init });
  if (r.status === 401) {
    window.location.href = "/login";
    throw new UnauthenticatedError("unauthenticated");
  }
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `${r.status} ${r.statusText}`);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/auth/me"),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  deleteJob: (id: string) => request<void>(`/api/jobs/${id}`, { method: "DELETE" }),
  submitUrls: (urls: string[], options: JobOptions) =>
    request<Job>("/api/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ urls, options }),
    }),
  submitFiles: (files: File[], options: JobOptions) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    fd.append("options_json", JSON.stringify(options));
    return request<Job>("/api/jobs/files", { method: "POST", body: fd });
  },
  downloadUrl: (id: string) => `/api/jobs/${id}/download`,
};
