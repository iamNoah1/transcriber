export type JobStatus = "queued" | "running" | "done" | "failed";

export interface JobOptions {
  formats: string[];
  model?: string | null;
}

export interface Job {
  id: string;
  status: JobStatus;
  input_kind: "urls" | "files";
  inputs: string[];
  options: JobOptions;
  message: string | null;
  file_count: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface User {
  open_id: string;
  name: string | null;
}
