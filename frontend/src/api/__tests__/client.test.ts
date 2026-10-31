import { describe, expect, it } from "vitest";
import {
  ApiError,
  createTask,
  getStatus,
  getVersionDiff,
} from "../client";
import {
  envelopeResponse,
  fail,
  mockFetch,
  ok,
} from "../../test/utils";
import type { SystemStatus } from "../types";

describe("api client", () => {
  it("unwraps a successful envelope and returns data", async () => {
    const status: SystemStatus = {
      featherless_configured: true,
      critic_configured: false,
      evaluator_mode: "subprocess",
      hidden_suite_encryption_available: true,
      publishing: "not available",
    };
    mockFetch((url) => {
      expect(url).toContain("/api/status");
      return envelopeResponse(ok(status));
    });

    await expect(getStatus()).resolves.toEqual(status);
  });

  it("throws a typed ApiError carrying code, status and details on 422", async () => {
    mockFetch(() =>
      envelopeResponse(
        fail("VALIDATION_ERROR", "Invalid body", [
          { field: "title", message: "required" },
        ]),
        { ok: false, status: 422 },
      ),
    );

    const err = await createTask({
      title: "",
      description: "x",
    }).catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.status).toBe(422);
    expect(err.details).toEqual([{ field: "title", message: "required" }]);
  });

  it("throws SUITE_UPLOAD_REJECTED with a top-level message and null details", async () => {
    mockFetch(() =>
      envelopeResponse(
        fail("SUITE_UPLOAD_REJECTED", "A check used a non-literal value.", null),
        { ok: false, status: 422 },
      ),
    );

    const err = await createTask({
      title: "t",
      description: "d",
    }).catch((e) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("SUITE_UPLOAD_REJECTED");
    expect(err.details).toBeNull();
    expect(err.message).toContain("non-literal");
  });

  it("maps a network failure to ApiError NETWORK_ERROR with status 0", async () => {
    mockFetch(() => {
      throw new TypeError("Failed to fetch");
    });

    const err = await getStatus().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("NETWORK_ERROR");
    expect(err.status).toBe(0);
  });

  it("handles a malformed (non-JSON) body on an error status", async () => {
    mockFetch(
      () =>
        ({
          ok: false,
          status: 500,
          json: async () => {
            throw new SyntaxError("Unexpected token");
          },
        }) as unknown as Response,
    );

    const err = await getStatus().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("INTERNAL_ERROR");
    expect(err.status).toBe(500);
  });

  it("encodes the diff query parameters", async () => {
    mockFetch((url) => {
      expect(url).toContain("/api/versions/v1/diff?against=parent");
      return envelopeResponse(
        ok({
          version_id: "v1",
          label: "V2",
          against: "parent",
          against_version_id: "v0",
          unified_diff: "",
          changelog: [],
        }),
      );
    });

    const diff = await getVersionDiff("v1", "parent");
    expect(diff.label).toBe("V2");
  });
});
