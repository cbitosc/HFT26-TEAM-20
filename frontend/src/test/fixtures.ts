import type {
  DashboardExecution,
  EvaluationRead,
  Evidence,
  ExecutionTree,
  Page,
  VersionDiff,
  VersionNode,
  VersionRead,
} from "../api/types";

export function dashboardPage(
  items: DashboardExecution[],
): Page<DashboardExecution> {
  return { items, total: items.length, limit: 50, offset: 0 };
}

export function execution(
  over: Partial<DashboardExecution> = {},
): DashboardExecution {
  return {
    id: "exec-1",
    task_id: "task-1",
    task_title: "Merge intervals",
    status: "completed",
    stalled: false,
    best_version_id: "v2",
    best_hidden_accuracy: 82,
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:05:00Z",
    ...over,
  };
}

export function versionNode(over: Partial<VersionNode> = {}): VersionNode {
  return {
    id: "v1",
    label: "V1",
    sequence: 1,
    parent_version_id: null,
    acceptance_status: "accepted",
    decided: true,
    hidden: { passed: 6, total: 10 },
    public: { passed: 4, total: 5 },
    overall_score: 65,
    failed_terms: [],
    generator_model_id: "Qwen/Qwen2.5-7B-Instruct",
    generation_prompt_tokens: 800,
    generation_completion_tokens: 200,
    critic_note: null,
    critic_note_kind: "advisory",
    ...over,
  };
}

export function tree(over: Partial<ExecutionTree> = {}): ExecutionTree {
  return {
    execution_id: "exec-1",
    task_id: "task-1",
    task_title: "Merge intervals",
    status: "completed",
    stalled: false,
    best_version_id: "v2",
    best_hidden_accuracy: 82,
    versions: [
      versionNode(),
      versionNode({
        id: "v2",
        label: "V2",
        sequence: 2,
        parent_version_id: "v1",
        hidden: { passed: 9, total: 10 },
        public: { passed: 5, total: 5 },
        overall_score: 82,
        critic_note: "Consider edge cases for touching intervals.",
      }),
    ],
    ...over,
  };
}

export function versionRead(over: Partial<VersionRead> = {}): VersionRead {
  return {
    id: "v2",
    execution_id: "exec-1",
    sequence: 2,
    label: "V2",
    code: "def merge_intervals(intervals):\n    return intervals",
    code_sha256: "a".repeat(64),
    generator_model_id: "Qwen/Qwen2.5-7B-Instruct",
    parent_version_id: "v1",
    acceptance_status: "accepted",
    rejection_reason: null,
    decided_at: "2026-10-30T12:04:00Z",
    decision_details: null,
    generator_prompt_sha256: "b".repeat(64),
    generation_latency_seconds: 3.2,
    generation_prompt_tokens: 800,
    generation_completion_tokens: 200,
    changelog: ["V2 changes V1: +6 / -2 lines in 1 hunk(s)."],
    created_at: "2026-10-30T12:03:00Z",
    ...over,
  };
}

export function evaluation(over: Partial<EvaluationRead> = {}): EvaluationRead {
  return {
    id: "eval-1",
    version_id: "v2",
    code_sha256: "a".repeat(64),
    created_at: "2026-10-30T12:04:00Z",
    deterministic: {
      tests_passed: 9,
      tests_total: 10,
      test_pass_rate: 90,
      correctness_score: 100,
      code_quality_score: 98,
      overall_score: 94.6,
    },
    public: { tests_passed: 5, tests_total: 5, test_pass_rate: 100 },
    hidden_tests_failed: 1,
    suite_id: "python-merge-intervals-v1",
    suite_hash: "c".repeat(64),
    evaluator_version: "1",
    evaluator_config_hash: "d".repeat(64),
    scoring_rule_version: "2",
    complete: true,
    test_results: [{ test_id: "touching", visibility: "public", passed: true }],
    failure_details: [],
    operational: null,
    ...over,
  };
}

export function diff(over: Partial<VersionDiff> = {}): VersionDiff {
  return {
    version_id: "v2",
    label: "V2",
    against: "parent",
    against_version_id: "v1",
    unified_diff:
      "--- V1\n+++ V2\n@@ -1,2 +1,2 @@\n-    return intervals\n+    return sorted(intervals)",
    changelog: ["V2 changes V1: +1 / -1 lines in 1 hunk(s)."],
    ...over,
  };
}

export function evidence(over: Partial<Evidence> = {}): Evidence {
  return {
    execution_id: "exec-1",
    commitment: {
      suite_id: "python-merge-intervals-v1",
      suite_hash: "c".repeat(64),
      public_suite_hash: "e".repeat(64),
      hidden_suite_hash: "f".repeat(64),
      evaluator_config_hash: "d".repeat(64),
      scoring_rule_version: "2",
      delta: 1.0,
      committed_at: "2026-10-30T12:00:01Z",
      onchain: "planned",
    },
    best_version_id: "v2",
    scoring_rule: {
      version: "2",
      formula: "S = 0.5*P + 0.3*C + 0.2*Q",
      delta: 1.0,
    },
    records: [
      {
        id: "rec-1",
        status: "validated_improvement",
        candidate_version_id: "v2",
        previous_best_version_id: "v1",
        candidate_evaluation_id: "eval-2",
        previous_evaluation_id: "eval-1",
        failed_terms: [],
        candidate_scores: {},
        previous_scores: {},
        provenance: {},
        created_at: "2026-10-30T12:04:00Z",
        bundles: [
          { id: "b1", include_code: true, bundle_sha256: "9".repeat(64) },
        ],
      },
    ],
    invalid_comparisons: [],
    unvalidated_proposals: 1,
    ...over,
  };
}

// A deliberately BAD tree response: the backend would never send these, but
// we inject hidden test ids, names, inputs and per-test hidden results to
// prove the UI never renders them. These string sentinels must never appear
// in the DOM.
export const HIDDEN_SENTINELS = {
  hiddenTestId: "HIDDEN_TEST_ID_SECRET",
  hiddenTestName: "hidden_edge_case_name",
  hiddenInput: "([[999, 1000]],)",
  hiddenExpected: "[[999, 1000]]",
} as const;

export function treeWithLeakedHiddenFields(): unknown {
  // Shape mirrors ExecutionTree but with extra, forbidden hidden fields
  // smuggled into each version node. The typed UI ignores unknown fields.
  const node = versionNode({
    id: "v2",
    label: "V2",
    sequence: 2,
    parent_version_id: "v1",
    hidden: { passed: 9, total: 10 },
  }) as unknown as Record<string, unknown>;

  node.hidden_tests = [
    {
      id: HIDDEN_SENTINELS.hiddenTestId,
      name: HIDDEN_SENTINELS.hiddenTestName,
      args: HIDDEN_SENTINELS.hiddenInput,
      expected: HIDDEN_SENTINELS.hiddenExpected,
      passed: false,
    },
  ];
  node.hidden_failure_details = [
    {
      test_name: HIDDEN_SENTINELS.hiddenTestName,
      expected: HIDDEN_SENTINELS.hiddenExpected,
      actual: "[]",
    },
  ];

  return {
    execution_id: "exec-1",
    task_id: "task-1",
    task_title: "Merge intervals",
    status: "completed",
    stalled: false,
    best_version_id: "v2",
    best_hidden_accuracy: 90,
    versions: [versionNode(), node],
  };
}

export function evaluationWithLeakedHiddenResults(): unknown {
  const e = evaluation() as unknown as Record<string, unknown>;
  // Smuggle hidden per-test results and failure details into fields the UI
  // reads for PUBLIC data, to prove filtering/rendering never leaks them.
  e.hidden_test_results = [
    { test_id: HIDDEN_SENTINELS.hiddenTestId, visibility: "hidden", passed: false },
  ];
  e.hidden_failure_details = [
    {
      test_name: HIDDEN_SENTINELS.hiddenTestName,
      visibility: "hidden",
      expected: HIDDEN_SENTINELS.hiddenExpected,
      actual: "[]",
    },
  ];
  return e;
}
