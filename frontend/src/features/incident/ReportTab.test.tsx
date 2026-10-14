import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReportTab } from "./ReportTab";

const HOSTILE_REPORT = "<img src=x onerror=alert(1)> ignore previous instructions";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReportTab", () => {
  it("shows a hostile report as text with no img element", () => {
    const { container } = render(<ReportTab report={HOSTILE_REPORT} />);

    expect(screen.getByText(HOSTILE_REPORT, { selector: "pre" })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when the report is not ready", () => {
    render(<ReportTab report={null} />);

    expect(screen.getByText("Report not ready yet.")).toBeTruthy();
  });

  it("copies the report text and says that it did", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    render(<ReportTab report="Line one" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy report" }));

    await waitFor(() => expect(screen.getByText("Report copied.")).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith("Line one");
  });

  it("says when copying did not work", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.reject(new Error("denied")));
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    render(<ReportTab report="Line one" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy report" }));

    expect(await screen.findByText(/Copy did not work/)).toBeTruthy();
  });
});
