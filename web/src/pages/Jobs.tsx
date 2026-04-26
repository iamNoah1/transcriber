import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api";
import type { Job } from "@/types";

const STATUS_CLASS: Record<Job["status"], string> = {
  queued: "bg-slate-200 text-slate-700",
  running: "bg-blue-200 text-blue-800",
  done: "bg-green-200 text-green-800",
  failed: "bg-red-200 text-red-800",
};

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);

  useEffect(() => {
    api.listJobs().then(setJobs).catch(() => setJobs([]));
  }, []);

  if (jobs === null) return null;

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Jobs</h1>
        <Link to="/" className="text-sm text-slate-600 hover:text-slate-900">+ New transcription</Link>
      </header>
      {jobs.length === 0 ? (
        <p className="text-slate-600">No jobs yet.</p>
      ) : (
        <ul className="space-y-2">
          {jobs.map((j) => (
            <li key={j.id} className="rounded-xl border border-slate-200 p-4 bg-white">
              <div className="flex items-center justify-between">
                <Link to={`/jobs/${j.id}`} className="font-medium">
                  {j.inputs[0] || "(no inputs)"}{j.inputs.length > 1 && ` +${j.inputs.length - 1}`}
                </Link>
                <span className={`px-2 py-0.5 rounded-full text-xs ${STATUS_CLASS[j.status]}`}>{j.status}</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">{new Date(j.created_at).toLocaleString()}</div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
