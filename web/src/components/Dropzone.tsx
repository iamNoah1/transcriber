import { useDropzone } from "react-dropzone";

import { cn } from "@/lib/utils";

type Props = {
  files: File[];
  onChange: (files: File[]) => void;
};

export function Dropzone({ files, onChange }: Props) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "audio/*": [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".webm"],
      "video/*": [".mp4"],
    },
    onDrop: (accepted) => onChange([...files, ...accepted]),
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition",
        isDragActive ? "border-slate-900 bg-slate-100" : "border-slate-300 hover:bg-slate-50"
      )}
    >
      <input {...getInputProps()} />
      {files.length === 0 ? (
        <p className="text-slate-600">Drop audio files here or click to pick</p>
      ) : (
        <ul className="text-left space-y-1">
          {files.map((f, i) => (
            <li key={i} className="text-sm text-slate-700">
              {f.name} <span className="text-slate-400">({Math.round(f.size / 1024)} KB)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
