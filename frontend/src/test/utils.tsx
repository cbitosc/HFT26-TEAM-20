import type { ReactElement } from "react";
import { render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { ApiEnvelope } from "../api/types";

export function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, refetchInterval: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: ReactElement,
  { route = "/" }: { route?: string } = {},
): RenderResult {
  const client = makeClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// Build a Response-like object for a mocked fetch.
export function envelopeResponse<T>(
  body: ApiEnvelope<T>,
  init: { ok?: boolean; status?: number } = {},
): Response {
  const status = init.status ?? (init.ok === false ? 400 : 200);
  const ok = init.ok ?? (status >= 200 && status < 300);
  return {
    ok,
    status,
    json: async () => body,
  } as unknown as Response;
}

export function ok<T>(data: T): ApiEnvelope<T> {
  return { success: true, data, error: null };
}

export function fail(
  code: string,
  message: string,
  details: { field: string; message: string }[] | null = null,
): ApiEnvelope<never> {
  return { success: false, data: null, error: { code, message, details } };
}

// Install a fetch mock that returns a queue of responses (or a single one).
export function mockFetch(
  responder: (url: string, init?: RequestInit) => Response | Promise<Response>,
): ReturnType<typeof vi.fn> {
  const fn = vi.fn(
    (input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(responder(String(input), init)),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
