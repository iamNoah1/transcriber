import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dropzone } from "./Dropzone";

describe("Dropzone", () => {
  it("renders empty state", () => {
    render(<Dropzone files={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/Drop audio files here/)).toBeInTheDocument();
  });

  it("renders filenames when present", () => {
    const f = new File(["x"], "hello.mp3", { type: "audio/mpeg" });
    render(<Dropzone files={[f]} onChange={vi.fn()} />);
    expect(screen.getByText(/hello\.mp3/)).toBeInTheDocument();
  });
});
