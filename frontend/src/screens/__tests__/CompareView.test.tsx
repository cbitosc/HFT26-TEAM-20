import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { CompareView } from "../CompareView";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import { diff, tree, versionNode, versionRead } from "../../test/fixtures";

function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/executions/:executionId/compare/:versionId"
        element={<CompareView />}
      />
    </Routes>,
    { route: "/executions/exec-1/compare/v2" },
  );
}

function responder(treeData: unknown) {
  return (url: string): Response => {
    if (url.includes("/tree")) return envelopeResponse(ok(treeData));
    if (url.includes("/diff")) return envelopeResponse(ok(diff()));
    if (url.includes("/versions/")) return envelopeResponse(ok(versionRead()));
    return envelopeResponse(ok({}));
  };
}

describe("CompareView", () => {
  it("shows a loading state", () => {
    mockFetch(() => new Promise(() => {}) as unknown as Response);
    renderAt();
    expect(screen.getByText(/loading comparison/i)).toBeInTheDocument();
  });

  it("shows an error state when the tree fails", async () => {
    mockFetch((url) => {
      if (url.includes("/tree"))
        return envelopeResponse(fail("EXECUTION_NOT_FOUND", "nope"), {
          ok: false,
          status: 404,
        });
      return envelopeResponse(ok(diff()));
    });
    renderAt();
    await waitFor(() =>
      expect(screen.getByText("EXECUTION_NOT_FOUND")).toBeInTheDocument(),
    );
  });

  it("renders the hidden headline, gate result, diff colours and changelog", async () => {
    mockFetch(responder(tree()));
    renderAt();

    // Hidden headline V1 60% -> V2 90%.
    await waitFor(() =>
      expect(screen.getByText(/60\.0%/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/90\.0%/)).toBeInTheDocument();
    // Gate accepted.
    expect(screen.getByText(/all gate terms held/i)).toBeInTheDocument();
    // Changelog entry.
    expect(
      screen.getByText(/V2 changes V1: \+1 \/ -1 lines/i),
    ).toBeInTheDocument();
  });

  it("warns when public improves but hidden does not", async () => {
    const t = tree({
      versions: [
        versionNode({ id: "v1", label: "V1", public: { passed: 4, total: 5 }, hidden: { passed: 6, total: 10 } }),
        versionNode({
          id: "v2",
          label: "V2",
          parent_version_id: "v1",
          acceptance_status: "rejected",
          failed_terms: [{ term: "aggregate_delta", message: "not enough" }],
          public: { passed: 5, total: 5 },
          hidden: { passed: 6, total: 10 },
        }),
      ],
    });
    mockFetch(responder(t));
    renderAt();

    await waitFor(() =>
      expect(
        screen.getByText(/public accuracy improved but hidden accuracy did not/i),
      ).toBeInTheDocument(),
    );
    // Failed term shown.
    expect(screen.getByText("aggregate_delta")).toBeInTheDocument();
  });

  it("toggles between diff-only and the full file", async () => {
    mockFetch(responder(tree()));
    renderAt();
    const user = userEvent.setup();

    const toggle = await screen.findByRole("button", {
      name: /show full file/i,
    });
    await user.click(toggle);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /show diff only/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/def merge_intervals/i)).toBeInTheDocument();
  });
});
