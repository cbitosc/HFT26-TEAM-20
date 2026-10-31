// Types mirror docs/API_CONTRACT.md. The dashboard treats hidden tests as
// counts only: there is deliberately no type anywhere that can carry a hidden
// test id, name, input, expected value or per-test hidden result.

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorBody | null;
}

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: ApiErrorDetail[] | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ---- Lifecycle ---------------------------------------------------------

export type ExecutionStatus =
  | "queued"
  | "generating_v1"
  | "evaluating_v1"
  | "critiquing"
  | "generating_v2"
  | "evaluating_v2"
  | "critiquing_v2"
  | "generating_v3"
  | "evaluating_v3"
  | "zk_proof"
  | "ipfs_publish"
  | "blockchain_register"
  | "completed"
  | "completed_no_improvement"
  | "failed"
  | "cancelled";

export const TERMINAL_STATUSES: ReadonlySet<ExecutionStatus> = new Set([
  "completed",
  "completed_no_improvement",
  "failed",
  "cancelled",
]);

export function isTerminal(status: ExecutionStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

// ---- Status strip ------------------------------------------------------

export interface SystemStatus {
  featherless_configured: boolean;
  critic_configured: boolean;
  evaluator_mode: "subprocess" | "disabled";
  hidden_suite_encryption_available: boolean;
  publishing: string; // always "not available" today
}

// ---- Dashboard executions ---------------------------------------------

export interface DashboardExecution {
  id: string;
  task_id: string;
  task_title: string;
  status: ExecutionStatus;
  stalled: boolean;
  best_version_id: string | null;
  best_hidden_accuracy: number | null; // hidden-suite pass rate 0..100
  created_at: string;
  updated_at: string;
}

// ---- Counts (hidden ALWAYS counts only) --------------------------------

export interface Counts {
  passed: number;
  total: number;
}

export interface FailedTerm {
  term: string;
  message: string;
}

// ---- Tree --------------------------------------------------------------

export interface VersionNode {
  id: string;
  label: string;
  sequence: number;
  parent_version_id: string | null;
  acceptance_status: "pending" | "accepted" | "rejected";
  decided: boolean;
  hidden: Counts | null;
  public: Counts | null;
  overall_score: number | null;
  failed_terms: FailedTerm[];
  generator_model_id: string | null;
  generation_prompt_tokens: number | null;
  generation_completion_tokens: number | null;
  critic_note: string | null;
  critic_note_kind: "advisory";
}

export interface ExecutionTree {
  execution_id: string;
  task_id: string;
  task_title: string;
  status: ExecutionStatus;
  stalled: boolean;
  best_version_id: string | null;
  best_hidden_accuracy: number | null;
  versions: VersionNode[];
}

// ---- Diff --------------------------------------------------------------

export interface VersionDiff {
  version_id: string;
  label: string;
  against: string;
  against_version_id: string | null;
  unified_diff: string;
  changelog: string[];
}

// ---- Version detail ----------------------------------------------------

export interface VersionRead {
  id: string;
  execution_id: string;
  sequence: number;
  label: string;
  code: string;
  code_sha256: string;
  generator_model_id: string | null;
  parent_version_id: string | null;
  acceptance_status: "pending" | "accepted" | "rejected";
  rejection_reason: string | null;
  decided_at: string | null;
  decision_details: unknown | null;
  generator_prompt_sha256: string | null;
  generation_latency_seconds: number | null;
  generation_prompt_tokens: number | null;
  generation_completion_tokens: number | null;
  changelog: string[];
  created_at: string;
}

// ---- Evaluation (public detail only; hidden as counts) -----------------

export interface PublicTestResult {
  test_id: string;
  visibility: "public";
  passed: boolean;
}

export interface PublicFailureDetail {
  test_name: string;
  visibility: "public";
  expected: string;
  actual: string;
  exception: string | null;
  traceback_excerpt: string[] | null;
}

export interface EvaluationRead {
  id: string;
  version_id: string;
  code_sha256: string;
  created_at: string;
  deterministic: {
    tests_passed: number; // hidden
    tests_total: number; // hidden
    test_pass_rate: number; // hidden pass rate
    correctness_score: number;
    code_quality_score: number;
    overall_score: number;
  };
  public: {
    tests_passed: number;
    tests_total: number;
    test_pass_rate: number | null;
  };
  hidden_tests_failed: number;
  suite_id: string;
  suite_hash: string;
  evaluator_version: string;
  evaluator_config_hash: string;
  scoring_rule_version: string;
  complete: boolean;
  // PUBLIC ONLY per the contract:
  test_results: PublicTestResult[];
  failure_details: PublicFailureDetail[];
  operational: unknown | null;
}

// ---- Commitment / evidence --------------------------------------------

export interface Commitment {
  suite_id: string;
  suite_hash: string;
  public_suite_hash: string;
  hidden_suite_hash: string;
  evaluator_config_hash: string;
  scoring_rule_version: string;
  delta: number;
  committed_at: string;
  onchain: string; // "planned"
}

export interface EvidenceRecord {
  id: string;
  status: "validated_improvement" | "rejected_attempt";
  candidate_version_id: string;
  previous_best_version_id: string | null;
  candidate_evaluation_id: string;
  previous_evaluation_id: string | null;
  failed_terms: FailedTerm[];
  candidate_scores: Record<string, unknown>;
  previous_scores: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
  bundles: { id: string; include_code: boolean; bundle_sha256: string }[];
}

export interface InvalidComparison {
  id: string;
  status: "invalid_comparison";
  candidate_version_id: string;
  previous_best_version_id: string | null;
  reasons: FailedTerm[];
  note: string;
  created_at: string;
}

export interface Evidence {
  execution_id: string;
  commitment: Commitment | null;
  best_version_id: string | null;
  scoring_rule: {
    version: string;
    formula: string;
    delta: number;
    [k: string]: unknown;
  };
  records: EvidenceRecord[];
  invalid_comparisons: InvalidComparison[];
  unvalidated_proposals: number;
}

// ---- Execution detail --------------------------------------------------

export interface ExecutionTransition {
  from_status: ExecutionStatus | null;
  to_status: ExecutionStatus;
  occurred_at: string;
}

export interface ExecutionRead {
  id: string;
  task_id: string;
  status: ExecutionStatus;
  max_revisions: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  best_version_id: string | null;
  error: { code: string; message: string; stage: string } | null;
  commitment: Commitment | null;
  run_claimed_at: string | null;
  stalled: boolean;
}

export interface ExecutionDetail extends ExecutionRead {
  transitions: ExecutionTransition[];
}

// ---- Task --------------------------------------------------------------

export interface SuiteSummary {
  id: string;
  source: "registered" | "uploaded";
  public_test_count: number;
  hidden_test_count: number;
  suite_hash: string;
  public_suite_hash: string;
  hidden_suite_hash: string;
}

export interface TaskRead {
  id: string;
  title: string;
  description: string;
  requirements: string[];
  language: string | null;
  category: string | null;
  evaluation_suite_id: string | null;
  starter_code: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  suite: SuiteSummary | null;
}

// ---- Suite upload (request-only shapes) --------------------------------

export type CheckKind = "returns" | "raises" | "unchanged_input" | "all_items_of_type";

export interface CheckUpload {
  kind: CheckKind;
  args: string; // literal tuple string
  expected?: string; // omitted for unchanged_input
}

export interface TestUpload {
  id: string;
  description: string;
  checks: CheckUpload[];
}

export interface SuiteUpload {
  entrypoint: string;
  language?: string;
  description?: string;
  contract: {
    arity: number;
    smoke_args: string;
    smoke_type: string;
  };
  max_complexity?: number;
  public_tests: TestUpload[];
  hidden_tests: TestUpload[];
}

export interface CreateTaskRequest {
  title: string;
  description: string;
  requirements?: string[];
  language?: string | null;
  category?: string | null;
  evaluation_suite_id?: string | null;
  suite?: SuiteUpload | null;
  starter_code?: string | null;
}
