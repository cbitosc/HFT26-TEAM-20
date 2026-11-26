import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { RunView } from "../RunView";
import {
  envelopeResponse,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import {
  HIDDEN_SENTINELS,
  evaluationWithLeakedHiddenResults,
  treeWithLeakedHiddenFields,
  versionRead,
} from "../../test/fixtures";

function renderRun() {
  return renderWithProviders(
    <Routes>
      <Route path="/executions/:executionId" element={<RunView />} />
    </Routes>,
    { route: "/executions/exec-1" },
  );
}

// The backend already strips hidden test contents; this test guards the UI.
// We feed a DELIBERATELY BAD response that smuggles hidden test ids, names,
// inputs, expected values and per-test hidden results, then assert none of
// them reaches the DOM. Hidden tests must only ever appear as counts.
describe("hidden test contents never render", () => {
  it("ignores leaked hidden fields in the tree and evaluation responses", async () => {
    mockFetch((url) => {
      if (url.includes("/tree"))
        return envelopeResponse(ok(treeWithLeakedHiddenFields()));
      if (url.endsWith("/evaluations"))
        return envelopeResponse(ok([evaluationWithLeakedHiddenResults()]));
      if (url.includes("/versions/"))
        return envelopeResponse(ok(versionRead()));
      return envelopeResponse(ok({}));
    });

    renderRun();

    // Wait until the detail panel has rendered counts, so the DOM is populated.
    await waitFor(() =>
      expect(
        screen.getByText(/9 of 10 hidden tests passed/i),
      ).toBeInTheDocument(),
    );

    const html = document.body.innerHTML;
    for (const sentinel of Object.values(HIDDEN_SENTINELS)) {
      expect(html).not.toContain(sentinel);
      expect(screen.queryByText(sentinel)).not.toBeInTheDocument();
    }
  });
});
