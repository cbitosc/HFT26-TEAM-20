// Typed fetch client. The ONLY way the dashboard reaches the backend.
// It unwraps the standard envelope and throws a typed ApiError on failure.

import type {
  ApiEnvelope,
  ApiErrorDetail,
  CreateTaskRequest,
  DashboardExecution,
  EvaluationRead,
  Evidence,
  ExecutionDetail,
  ExecutionRead,
  ExecutionTree,
  Page,
  SystemStatus,
  TaskRead,
  VersionDiff,
  VersionRead,
} from "./types";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: ApiErrorDetail[] | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details: ApiErrorDetail[] | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function resolveBaseUrl(): string {
  const raw =
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
    "http://localhost:8000";
  // Strip trailing slashes; the client appends /api itself.
  return raw.replace(/\/+$/, "");
}

const API_ROOT = `${resolveBaseUrl()}/api`;

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = opts;

  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch {
    // Network failure, CORS rejection, backend down, etc.
    throw new ApiError(
      "NETWORK_ERROR",
      "Could not reach the backend. Is it running on the configured URL?",
      0,
      null,
    );
  }

  let envelope: ApiEnvelope<T> | null = null;
  try {
    envelope = (await response.json()) as ApiEnvelope<T>;
  } catch {
    envelope = null;
  }

  if (!response.ok || !envelope || envelope.success === false) {
    const err = envelope?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      err?.details ?? null,
    );
  }

  // success === true. data may legitimately be null for some payloads,
  // but all endpoints used here return an object.
  return envelope.data as T;
}

// ---- Dashboard / status ------------------------------------------------

export function getStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return request<SystemStatus>("/status", { signal });
}

export function getDashboardExecutions(
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<Page<DashboardExecution>> {
  const q = new URLSearchParams();
  if (params.limit !== undefined) q.set("limit", String(params.limit));
  if (params.offset !== undefined) q.set("offset", String(params.offset));
  const qs = q.toString();
  return request<Page<DashboardExecution>>(
    `/dashboard/executions${qs ? `?${qs}` : ""}`,
    { signal },
  );
}

// ---- Executions --------------------------------------------------------

export function getExecution(
  id: string,
  signal?: AbortSignal,
): Promise<ExecutionDetail> {
  return request<ExecutionDetail>(`/executions/${encodeURIComponent(id)}`, {
    signal,
  });
}

export function getExecutionTree(
  id: string,
  signal?: AbortSignal,
): Promise<ExecutionTree> {
  return request<ExecutionTree>(
    `/executions/${encodeURIComponent(id)}/tree`,
    { signal },
  );
}

export function getEvidence(
  id: string,
  signal?: AbortSignal,
): Promise<Evidence> {
  return request<Evidence>(
    `/executions/${encodeURIComponent(id)}/evidence`,
    { signal },
  );
}

export function cancelExecution(id: string): Promise<ExecutionDetail> {
  return request<ExecutionDetail>(
    `/executions/${encodeURIComponent(id)}/cancel`,
    { method: "POST", body: {} },
  );
}

export function runExecution(id: string): Promise<ExecutionRead> {
  return request<ExecutionRead>(
    `/executions/${encodeURIComponent(id)}/run`,
    { method: "POST", body: {} },
  );
}

// ---- Versions ----------------------------------------------------------

export function getVersionDiff(
  versionId: string,
  against: string = "parent",
  signal?: AbortSignal,
): Promise<VersionDiff> {
  return request<VersionDiff>(
    `/versions/${encodeURIComponent(versionId)}/diff?against=${encodeURIComponent(against)}`,
    { signal },
  );
}

export function getVersion(
  versionId: string,
  signal?: AbortSignal,
): Promise<VersionRead> {
  return request<VersionRead>(
    `/versions/${encodeURIComponent(versionId)}`,
    { signal },
  );
}

export function getVersionEvaluations(
  versionId: string,
  signal?: AbortSignal,
): Promise<EvaluationRead[]> {
  return request<EvaluationRead[]>(
    `/versions/${encodeURIComponent(versionId)}/evaluations`,
    { signal },
  );
}

// ---- Tasks -------------------------------------------------------------

export function createTask(body: CreateTaskRequest): Promise<TaskRead> {
  return request<TaskRead>("/tasks", { method: "POST", body });
}

export function createExecution(taskId: string): Promise<ExecutionRead> {
  return request<ExecutionRead>(
    `/tasks/${encodeURIComponent(taskId)}/executions`,
    { method: "POST", body: {} },
  );
}

export const __testing = { API_ROOT };
