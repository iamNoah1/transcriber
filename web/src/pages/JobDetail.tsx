import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api";
import type { Job } from "@/types";

const STATUS_STYLES: Record<Job["status"], { dot: string; badge: string }> = {
  queued:  { dot: "bg-slate-400",              badge: "bg-slate-100 text-slate-700" },
  running: { dot: "bg-blue-500 animate-pulse", badge: "bg-blue-100 text-blue-800"  },
  done:    { dot: "bg-green-500",              badge: "bg-green-100 text-green-800" },
  failed:  { dot: "bg-red-500",               badge: "bg-red-100 text-red-800"    },
};

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function fmtDuration(a: string | null, b: string | null) {
  if (!a || !b) return null;
  const ms = new Date(b).getTime() - new Date(a).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function tick() {
      try {
        const j = await api.getJob(id!);
        if (!cancelled) setJob(j);
        if (!cancelled && (j.status === "queued" || j.status === "running")) {
          setTimeout(tick, 2000);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    tick();
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return (
      <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
        <Link to="/jobs" className="text-sm text-slate-600 hover:text-slate-900">← All jobs</Link>
        <p className="text-red-600 text-sm">{error}</p>
      </main>
    );
  }

  if (!job) return null;

  const style = STATUS_STYLES[job.status];
  const duration = fmtDuration(job.started_at, job.finished_at);

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
      <Link to="/jobs" className="text-sm text-slate-600 hover:text-slate-900">← All jobs</Link>

      <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-5">

        {/* Status row */}
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${style.dot}`} />
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${style.badge}`}>
            {job.status}
          </span>
          <span className="text-xs font-mono text-slate-400 ml-auto truncate max-w-[14rem]">{job.id}</span>
        </div>

        {/* Inputs */}
        <div>
          <h2 className="text-sm font-medium text-slate-900 mb-1">Input files</h2>
          <ul className="text-sm text-slate-600 list-disc list-inside space-y-0.5">
            {job.inputs.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>

        {/* Options */}
        <div className="text-xs text-slate-500 flex gap-3">
          <span>formats: <span className="text-slate-700">{job.options.formats.join(", ")}</span></span>
          <span>model: <span className="text-slate-700">{job.options.model || "auto"}</span></span>
        </div>

        {/* Live message / log */}
        {job.message && (
          <div className={`rounded-lg border px-4 py-3 text-sm ${
            job.status === "failed"
              ? "bg-red-50 border-red-200 text-red-700"
              : job.status === "running"
              ? "bg-blue-50 border-blue-200 text-blue-800"
              : "bg-slate-50 border-slate-200 text-slate-600"
          }`}>
            {job.status === "running" && (
              <span className="mr-2 inline-block w-3 h-3 rounded-full bg-blue-400 animate-pulse align-middle" />
            )}
            {job.message}
          </div>
        )}

        {/* Timeline */}
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <div className="font-medium text-slate-500 uppercase tracking-wide mb-0.5">Submitted</div>
            <div className="text-slate-700">{fmtDate(job.created_at)}</div>
          </div>
          <div>
            <div className="font-medium text-slate-500 uppercase tracking-wide mb-0.5">Started</div>
            <div className="text-slate-700">{fmtDate(job.started_at)}</div>
          </div>
          <div>
            <div className="font-medium text-slate-500 uppercase tracking-wide mb-0.5">Finished</div>
            <div className="text-slate-700">
              {fmtDate(job.finished_at)}
              {duration && <span className="ml-1 text-slate-400">({duration})</span>}
            </div>
          </div>
        </div>

        {/* Download */}
        {job.status === "done" && (
          <a
            href={api.downloadUrl(job.id)}
            className="inline-block rounded-xl bg-slate-900 text-white font-medium px-4 py-2 hover:bg-slate-800 transition"
          >
            Download
            {job.file_count && job.file_count > 1 ? ` (${job.file_count} files)` : ""}
          </a>
        )}
      </div>
    </main>
  );
}
