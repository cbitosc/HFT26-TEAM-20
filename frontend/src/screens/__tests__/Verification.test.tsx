import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { Verification } from "../Verification";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import { evidence } from "../../test/fixtures";

function renderAt() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/executions/:executionId/verification"
        element={<Verification />}
      />
    </Routes>,
    { route: "/executions/exec-1/verification" },
  );
}

describe("Verification", () => {
  it("shows a loading state", () => {
    mockFetch(() => new Promise(() => {}) as unknown as Response);
    renderAt();
    expect(screen.getByText(/loading evidence/i)).toBeInTheDocument();
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

  it("renders commitment hashes, scoring rule and evidence records read-only", async () => {
    mockFetch(() => envelopeResponse(ok(evidence())));
    renderAt();

    await waitFor(() =>
      expect(screen.getByText("python-merge-intervals-v1")).toBeInTheDocument(),
    );
    expect(screen.getByText("S = 0.5*P + 0.3*C + 0.2*Q")).toBeInTheDocument();
    expect(screen.getByText("validated_improvement")).toBeInTheDocument();
    expect(screen.getByText(/1 unvalidated Critic proposal/i)).toBeInTheDocument();
  });

  it("renders empty commitment and empty records gracefully", async () => {
    mockFetch(() =>
      envelopeResponse(
        ok(
          evidence({
            commitment: null,
            records: [],
            invalid_comparisons: [],
            unvalidated_proposals: 0,
          }),
        ),
      ),
    );
    renderAt();
    await waitFor(() =>
      expect(
        screen.getByText(/no commitment recorded/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/no decided evidence records/i)).toBeInTheDocument();
  });
});
