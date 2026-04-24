import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api";
import type { Job } from "@/types";

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

  if (error) return <main className="p-8">{error}</main>;
  if (!job) return null;

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Job</h1>
        <Link to="/jobs" className="text-sm text-slate-600 underline">All jobs</Link>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-500">{job.id}</span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100">{job.status}</span>
        </div>
        <div>
          <h2 className="text-sm font-medium">Inputs</h2>
          <ul className="text-sm text-slate-700 list-disc list-inside">
            {job.inputs.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
        {job.message && <p className="text-sm text-slate-600">{job.message}</p>}
        {job.status === "done" && (
          <a
            href={api.downloadUrl(job.id)}
            className="inline-block rounded-xl bg-slate-900 text-white font-medium px-4 py-2 hover:bg-slate-800"
          >
            Download{job.file_count && job.file_count > 1 ? " (zip)" : ""}
          </a>
        )}
        {job.status === "failed" && <p className="text-sm text-red-600">{job.message}</p>}
      </div>
    </main>
  );
}
