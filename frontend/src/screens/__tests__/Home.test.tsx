import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Home } from "../Home";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import { dashboardPage, execution } from "../../test/fixtures";

describe("Home", () => {
  it("shows a loading state first", () => {
    mockFetch(() => new Promise(() => {}) as unknown as Response);
    renderWithProviders(<Home />);
    expect(screen.getByText(/loading executions/i)).toBeInTheDocument();
  });

  it("renders an error state with the error code and a retry", async () => {
    mockFetch(() =>
      envelopeResponse(fail("INTERNAL_ERROR", "boom"), {
        ok: false,
        status: 500,
      }),
    );
    renderWithProviders(<Home />);
    await waitFor(() =>
      expect(screen.getByText("INTERNAL_ERROR")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("renders an empty state when there are no executions", async () => {
    mockFetch(() => envelopeResponse(ok(dashboardPage([]))));
    renderWithProviders(<Home />);
    await waitFor(() =>
      expect(screen.getByText(/no executions yet/i)).toBeInTheDocument(),
    );
  });

  it("renders rows with best hidden accuracy and a stalled flag", async () => {
    mockFetch(() =>
      envelopeResponse(
        ok(
          dashboardPage([
            execution({ id: "e1", task_title: "Merge intervals", best_hidden_accuracy: 82 }),
            execution({
              id: "e2",
              task_title: "Stalled job",
              status: "generating_v2",
              stalled: true,
              best_hidden_accuracy: null,
            }),
          ]),
        ),
      ),
    );
    renderWithProviders(<Home />);

    await waitFor(() =>
      expect(screen.getByText("Merge intervals")).toBeInTheDocument(),
    );
    expect(screen.getByText("82.0%")).toBeInTheDocument();
    expect(screen.getByText("Stalled job")).toBeInTheDocument();
    expect(screen.getByText("stalled")).toBeInTheDocument();
    // null accuracy renders as a dash.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
