import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Dropzone } from "@/components/Dropzone";
import { api } from "@/api";
import type { JobOptions } from "@/types";

const FORMATS = ["txt", "srt", "vtt", "json", "tsv"] as const;
const MODELS = ["", "tiny", "base", "medium", "large"] as const;

export default function Home() {
  const nav = useNavigate();
  const [urlsText, setUrlsText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [formats, setFormats] = useState<string[]>(["txt"]);
  const [model, setModel] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const urls = urlsText
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const canSubmit = (urls.length > 0 || files.length > 0) && formats.length > 0 && !submitting;

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const options: JobOptions = { formats, model: model || null };
      const job = files.length > 0
        ? await api.submitFiles(files, options)
        : await api.submitUrls(urls, options);
      nav(`/jobs/${job.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  function toggle(fmt: string) {
    setFormats((f) => (f.includes(fmt) ? f.filter((x) => x !== fmt) : [...f, fmt]));
  }

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto space-y-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">transcribe-cloud</h1>
        <a href="/jobs" className="text-sm text-slate-600 underline">Jobs</a>
      </header>

      <section className="space-y-2">
        <label className="text-sm font-medium">YouTube URLs (one per line)</label>
        <textarea
          className="w-full min-h-[120px] rounded-xl border border-slate-300 p-3 font-mono text-sm"
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          placeholder={"https://youtu.be/...\nhttps://youtube.com/playlist?list=..."}
        />
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">…or audio files</label>
        <Dropzone files={files} onChange={setFiles} />
      </section>

      <section className="grid grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-sm font-medium">Output formats</label>
          <div className="flex flex-wrap gap-2">
            {FORMATS.map((f) => (
              <button
                type="button"
                key={f}
                onClick={() => toggle(f)}
                className={
                  "px-3 py-1 rounded-full text-sm border " +
                  (formats.includes(f)
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-700 border-slate-300")
                }
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Model (auto if unset)</label>
          <select
            className="rounded-xl border border-slate-300 px-3 py-2 w-full"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>{m || "auto"}</option>
            ))}
          </select>
        </div>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        disabled={!canSubmit}
        onClick={submit}
        className="w-full rounded-xl bg-slate-900 text-white font-medium py-3 disabled:opacity-40 hover:bg-slate-800 transition"
      >
        {submitting ? "Submitting…" : "Transcribe"}
      </button>
    </main>
  );
}
