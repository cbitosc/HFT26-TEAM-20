import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { NewTask } from "../NewTask";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
  renderWithProviders,
} from "../../test/utils";
import type { TaskRead } from "../../api/types";

function taskRead(): TaskRead {
  return {
    id: "task-1",
    title: "Square",
    description: "Implement f(x).",
    requirements: [],
    language: "python",
    category: null,
    evaluation_suite_id: null,
    starter_code: null,
    status: "active",
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:00:00Z",
    suite: {
      id: "u123abc",
      source: "uploaded",
      public_test_count: 1,
      hidden_test_count: 1,
      suite_hash: "SUITEHASH" + "0".repeat(55),
      public_suite_hash: "PUBHASH" + "0".repeat(57),
      hidden_suite_hash: "HIDHASH" + "0".repeat(57),
    },
  };
}

async function fillValidForm(user: UserEvent) {
  await user.type(screen.getByLabelText("Title"), "Square");
  await user.type(screen.getByLabelText("Description"), "Implement f(x).");
  await user.type(screen.getByLabelText("Entry function"), "f");

  // The per-test rows share placeholders; [0] is the public test, [1] hidden.
  const argsInputs = screen.getAllByPlaceholderText("([(1, 3), (2, 6)],)");
  await user.type(argsInputs[0], "(2,)");
  await user.type(argsInputs[1], "(3,)");

  // Expected values for the default "returns" kind.
  const expectedInputs = screen.getAllByPlaceholderText("[(1, 6)]");
  await user.type(expectedInputs[0], "4");
  await user.type(expectedInputs[1], "9");
}

describe("NewTask", () => {
  it("disables Start Run until required fields and tests exist, and flags the single-check limit", () => {
    mockFetch(() => envelopeResponse(ok({})));
    renderWithProviders(<NewTask />);

    expect(
      screen.getByRole("button", { name: /start run/i }),
    ).toBeDisabled();
    expect(
      screen.getByText(/exactly one check per test/i),
    ).toBeInTheDocument();
  });

  it("runs create-task -> create-execution -> run on confirm and shows only counts and hashes", async () => {
    const calls: string[] = [];
    mockFetch((url) => {
      calls.push(url);
      if (url.endsWith("/api/tasks")) {
        return envelopeResponse(ok(taskRead()), { status: 201 });
      }
      if (url.includes("/tasks/task-1/executions")) {
        return envelopeResponse(
          ok({ id: "exec-1", status: "queued" }),
          { status: 201 },
        );
      }
      if (url.includes("/executions/exec-1/run")) {
        return envelopeResponse(
          ok({ id: "exec-1", status: "generating_v1" }),
          { status: 202 },
        );
      }
      return envelopeResponse(ok({}));
    });

    const user = userEvent.setup();
    renderWithProviders(<NewTask />);
    await fillValidForm(user);

    const start = screen.getByRole("button", { name: /start run/i });
    await waitFor(() => expect(start).toBeEnabled());
    await user.click(start);

    // Confirmation states the hash/configuration are recorded before generation.
    const dialog = await screen.findByRole("dialog", { name: /confirm run/i });
    expect(
      within(dialog).getByText(/before any code is generated/i),
    ).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("button", { name: /confirm and start/i }),
    );

    // Success panel shows counts and hashes only.
    await screen.findByText(/run started/i);
    expect(screen.getByText(/SUITEHASH/)).toBeInTheDocument();
    expect(screen.getByText(/PUBHASH/)).toBeInTheDocument();
    expect(screen.getByText(/HIDHASH/)).toBeInTheDocument();
    expect(screen.getByText("u123abc")).toBeInTheDocument();
    // Both counts (public and hidden) are shown as "1".
    expect(screen.getAllByText("1", { selector: "dd" })).toHaveLength(2);

    // The three write calls happened in order.
    const writeCalls = calls.filter(
      (c) =>
        c.endsWith("/api/tasks") ||
        c.includes("/executions") ,
    );
    expect(writeCalls[0]).toMatch(/\/api\/tasks$/);
    expect(writeCalls[1]).toMatch(/\/tasks\/task-1\/executions$/);
    expect(writeCalls[2]).toMatch(/\/executions\/exec-1\/run$/);

    // The hidden test args we typed are NOT echoed back anywhere.
    expect(screen.queryByText(/\(3,\)/)).not.toBeInTheDocument();
  });

  it("renders a 422 with both per-field details and a top-level message", async () => {
    mockFetch((url) => {
      if (url.endsWith("/api/tasks")) {
        return envelopeResponse(
          fail("VALIDATION_ERROR", "Invalid body", [
            { field: "suite.public_tests.0.args", message: "must be a tuple" },
          ]),
          { ok: false, status: 422 },
        );
      }
      return envelopeResponse(ok({}));
    });

    const user = userEvent.setup();
    renderWithProviders(<NewTask />);
    await fillValidForm(user);

    await user.click(screen.getByRole("button", { name: /start run/i }));
    const dialog = await screen.findByRole("dialog", { name: /confirm run/i });
    await user.click(
      within(dialog).getByRole("button", { name: /confirm and start/i }),
    );

    await waitFor(() =>
      expect(screen.getByText("VALIDATION_ERROR")).toBeInTheDocument(),
    );
    expect(screen.getByText("Invalid body")).toBeInTheDocument();
    expect(screen.getByText(/must be a tuple/i)).toBeInTheDocument();
  });
});
