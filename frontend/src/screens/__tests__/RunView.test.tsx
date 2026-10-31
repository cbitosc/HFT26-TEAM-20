import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { RunView } from "../RunView";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import { evaluation, tree, versionRead } from "../../test/fixtures";

function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route path="/executions/:executionId" element={<RunView />} />
    </Routes>,
    { route: "/executions/exec-1" },
  );
}

// Route a mocked fetch by URL to the right fixture.
function routingResponder(treeData: unknown) {
  return (url: string): Response => {
    if (url.includes("/tree")) return envelopeResponse(ok(treeData));
    if (url.endsWith("/evaluations"))
      return envelopeResponse(ok([evaluation()]));
    if (url.includes("/versions/")) return envelopeResponse(ok(versionRead()));
    return envelopeResponse(ok({}));
  };
}

describe("RunView", () => {
  it("shows a loading state", () => {
    mockFetch(() => new Promise(() => {}) as unknown as Response);
    renderAt();
    expect(screen.getByText(/loading run/i)).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    mockFetch(() =>
      envelopeResponse(fail("EXECUTION_NOT_FOUND", "nope"), {
        ok: false,
        status: 404,
      }),
    );
    renderAt();
    await waitFor(() =>
      expect(screen.getByText("EXECUTION_NOT_FOUND")).toBeInTheDocument(),
    );
  });

  it("shows an empty versions state for a run with no versions", async () => {
    mockFetch(
      routingResponder(tree({ versions: [], best_version_id: null, status: "queued" })),
    );
    renderAt();
    await waitFor(() =>
      expect(screen.getByText(/no versions generated yet/i)).toBeInTheDocument(),
    );
  });

  it("renders versions, hidden counts, advisory critic note and public results", async () => {
    mockFetch(routingResponder(tree()));
    renderAt();

    await waitFor(() =>
      expect(screen.getByText("Merge intervals")).toBeInTheDocument(),
    );
    // Both version labels appear as nodes.
    expect(screen.getByText("V1")).toBeInTheDocument();
    // Advisory label on the critic note (best version v2 selected by default).
    await waitFor(() =>
      expect(screen.getByText(/consider edge cases/i)).toBeInTheDocument(),
    );
    expect(screen.getAllByText("advisory").length).toBeGreaterThan(0);
    // Hidden shown as counts only.
    expect(
      screen.getByText(/9 of 10 hidden tests passed/i),
    ).toBeInTheDocument();
    // Public test result row.
    await waitFor(() =>
      expect(screen.getByText("touching")).toBeInTheDocument(),
    );
  });

  it("offers a Cancel button and a stalled note for a non-terminal, stalled run", async () => {
    mockFetch(
      routingResponder(
        tree({ status: "generating_v2", stalled: true }),
      ),
    );
    renderAt();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /cancel run/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/claimed by an earlier server process/i)).toBeInTheDocument();
  });

  it("hides the Cancel button for a terminal run", async () => {
    mockFetch(routingResponder(tree({ status: "completed" })));
    renderAt();
    await waitFor(() =>
      expect(screen.getByText("Merge intervals")).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: /cancel run/i }),
    ).not.toBeInTheDocument();
  });
});
