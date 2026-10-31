// React Query hooks. Polling hooks stop automatically once an execution
// reaches a terminal status.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  cancelExecution,
  createExecution,
  createTask,
  getDashboardExecutions,
  getEvidence,
  getExecution,
  getExecutionTree,
  getStatus,
  getVersion,
  getVersionDiff,
  getVersionEvaluations,
  getMemory,
  createTransferExperiment,
  getTransferExperiment,
  deleteTask,
  runExecution,
} from "./client";
import {
  isTerminal,
  type CreateTaskRequest,
  type DashboardExecution,
  type EvaluationRead,
  type Evidence,
  type ExecutionDetail,
  type ExecutionTree,
  type Memory,
  type Page,
  type SystemStatus,
  type TaskRead,
  type TransferExperiment,
  type VersionDiff,
  type VersionRead,
} from "./types";

const POLL_MS = 3000;

export function useMemory(category?: string): UseQueryResult<Memory[]> {
  return useQuery({
    queryKey: ["memory", category ?? null],
    queryFn: ({ signal }) => getMemory({ category, limit: 50 }, signal),
  });
}

export function useTransferExperiment(
  id: string | undefined,
): UseQueryResult<TransferExperiment> {
  return useQuery({
    queryKey: ["transfer-experiment", id],
    queryFn: ({ signal }) => getTransferExperiment(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const m = query.state.data?.metrics;
      if (!m) return POLL_MS;
      return m.control.terminal && m.treatment.terminal ? false : POLL_MS;
    },
  });
}

export function useCreateTransferExperiment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { base_task_id: string; start?: boolean }) =>
      createTransferExperiment(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memory"] });
    },
  });
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-executions"] });
    },
  });
}

export function useStatus(): UseQueryResult<SystemStatus> {
  return useQuery({
    queryKey: ["status"],
    queryFn: ({ signal }) => getStatus(signal),
    refetchInterval: 15000,
    staleTime: 10000,
  });
}

export function useDashboardExecutions(
  limit = 50,
  offset = 0,
): UseQueryResult<Page<DashboardExecution>> {
  return useQuery({
    queryKey: ["dashboard-executions", limit, offset],
    queryFn: ({ signal }) => getDashboardExecutions({ limit, offset }, signal),
    refetchInterval: POLL_MS,
  });
}

export function useExecutionTree(
  id: string | undefined,
): UseQueryResult<ExecutionTree> {
  return useQuery({
    queryKey: ["execution-tree", id],
    queryFn: ({ signal }) => getExecutionTree(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return POLL_MS;
      return isTerminal(data.status) ? false : POLL_MS;
    },
  });
}

export function useExecution(
  id: string | undefined,
): UseQueryResult<ExecutionDetail> {
  return useQuery({
    queryKey: ["execution", id],
    queryFn: ({ signal }) => getExecution(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return POLL_MS;
      return isTerminal(data.status) ? false : POLL_MS;
    },
  });
}

export function useEvidence(
  id: string | undefined,
): UseQueryResult<Evidence> {
  return useQuery({
    queryKey: ["evidence", id],
    queryFn: ({ signal }) => getEvidence(id as string, signal),
    enabled: Boolean(id),
  });
}

export function useVersionDiff(
  versionId: string | undefined,
  against = "parent",
): UseQueryResult<VersionDiff> {
  return useQuery({
    queryKey: ["version-diff", versionId, against],
    queryFn: ({ signal }) => getVersionDiff(versionId as string, against, signal),
    enabled: Boolean(versionId),
  });
}

export function useVersion(
  versionId: string | undefined,
): UseQueryResult<VersionRead> {
  return useQuery({
    queryKey: ["version", versionId],
    queryFn: ({ signal }) => getVersion(versionId as string, signal),
    enabled: Boolean(versionId),
  });
}

export function useVersionEvaluations(
  versionId: string | undefined,
): UseQueryResult<EvaluationRead[]> {
  return useQuery({
    queryKey: ["version-evaluations", versionId],
    queryFn: ({ signal }) => getVersionEvaluations(versionId as string, signal),
    enabled: Boolean(versionId),
  });
}

export function useCancelExecution(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => cancelExecution(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["execution", id] });
      void qc.invalidateQueries({ queryKey: ["execution-tree", id] });
      void qc.invalidateQueries({ queryKey: ["dashboard-executions"] });
    },
  });
}

// Create task -> create execution -> run, as one flow for the New Task screen.
export interface StartRunResult {
  task: TaskRead;
  executionId: string;
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation<StartRunResult, Error, CreateTaskRequest>({
    mutationFn: async (req) => {
      const task = await createTask(req);
      const execution = await createExecution(task.id);
      await runExecution(execution.id);
      return { task, executionId: execution.id };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["dashboard-executions"] });
    },
  });
}

export { runExecution, createTask, createExecution };
