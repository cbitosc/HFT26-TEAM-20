# AutoEvolve Protocol — Cross-Agent Memory Experiment Design

**Version:** 2.0  
**Date:** October 30, 2026

---

## 1. Objective

Design a controlled experiment demonstrating that Agent 2 can inherit and apply knowledge from Agent 1's execution, with measurable performance improvement compared to a baseline without memory inheritance.

---

## 2. Experiment Requirements

### 2.1 Controlled Comparison

The no-memory and with-memory runs MUST use:
- **Same task** — Identical task description
- **Same evaluator** — Same test suite, same evaluation logic
- **Same model configuration** — Same model, same temperature, same settings
- **Same generation settings** — Same max tokens, same parameters

### 2.2 What Must Be Recorded

For each run, explicitly record:
1. **Inherited lessons** — What patterns/insights were retrieved
2. **Evaluation outputs** — Actual scores for each version
3. **Comparison data** — Side-by-side metrics

---

## 3. Experiment Design

### 3.1 Three-Scenario Comparison

| Scenario | Description | Purpose |
|----------|-------------|---------|
| **Agent 1** | Original task execution | Create and store memory |
| **Agent 2 (No Memory)** | Same task, fresh execution | Baseline for comparison |
| **Agent 2 (With Memory)** | Same task, with inherited knowledge | Test knowledge transfer |

### 3.2 Task Selection

Use the **exact same task** for both Agent 2 runs to ensure valid comparison:

**Task:** "Implement a function to sort an array of integers in ascending order using an efficient algorithm."

This is specific and measurable.

---

## 4. Experiment Steps

### Phase 1: Agent 1 — Create Memory

```
Task: "Implement a function to sort an array of integers 
       in ascending order using an efficient algorithm."

1. Generate V1: Insertion sort (score: 68)
   - Test pass rate: 80%
   - Correctness: 80%
   - Code quality: 50%

2. Evaluate V1: Correct but O(n²) time complexity

3. Critique: "Consider using a divide-and-conquer approach
   like quicksort or mergesort for better time complexity"

4. Generate V2: Quicksort (score: 88)
   - Test pass rate: 100%
   - Correctness: 90%
   - Code quality: 80%

5. Improvement: +20 points (68 → 88)

6. Store Memory:
   - task_type: "array_sorting"
   - pattern: "use_divide_and_conquer"
   - insight: "quicksort/mergesort achieve O(n log n) vs O(n²)"
   - successful_approach: "quicksort"
   - failed_approach: "insertion_sort"
   - source_execution_id: "agent1-execution-uuid"
```

### Phase 2: Agent 2 — Baseline (No Memory)

```
Task: Same as Agent 1: "Implement a function to sort an array 
       of integers in ascending order using an efficient algorithm."

Configuration: Identical to Agent 1 (same model, same settings)

1. Retrieve memory: NONE (control baseline)

2. Generate V1: Selection sort (score: 72)
   - Test pass rate: 85%
   - Correctness: 80%
   - Code quality: 55%

3. Critique: Generic improvement suggestions

4. Generate V2: Improved selection sort (score: 82)

5. Improvement: +10 points (72 → 82)
```

### Phase 3: Agent 2 — With Memory

```
Task: Same as Agent 1: "Implement a function to sort an array 
       of integers in ascending order using an efficient algorithm."

Configuration: Identical to Agent 1 (same model, same settings)

1. Retrieve memory:
   - Query: task_type="array_sorting"
   - Get: pattern="use_divide_and_conquer"
   - Include in prompt: "Consider divide-and-conquer approach"

2. Generate V1: Quicksort (score: 86)
   - Test pass rate: 100%
   - Correctness: 90%
   - Code quality: 75%

3. Improvement: +14 points vs baseline V1 (86 vs 72)
   - More direct path to solution

4. (Optional) Generate V2: Further optimized (score: 90)
```

---

## 5. Measurement and Comparison

### 5.1 Metrics

| Metric | Agent 2 (No Memory) | Agent 2 (With Memory) | Difference |
|--------|---------------------|----------------------|------------|
| V1 Score | 72 | 86 | +14 |
| V2 Score | 82 | 90 | +8 |
| Total Improvement | +10 | +4 (+90 w/ V1) | — |
| Iterations to solution | 2 | 1 | -1 |
| Memory retrieved | N/A | 1 record | — |

### 5.2 What This Demonstrates

1. **Memory retrieval works** — Agent 2 successfully queries and receives relevant memory
2. **Pattern application** — Agent 2's prompt includes learned pattern
3. **Performance improvement** — V1 score is higher with memory than without

### 5.3 Important Caveat

> **Statistical Limitation:** This is ONE comparison, not statistically significant evidence of general improvement. It demonstrates the mechanism works, not that it always works.

---

## 6. API Endpoints

### 6.1 Store Memory

**POST** `/api/memory/store`

Request:
```json
{
  "execution_id": "agent1-execution-uuid",
  "task_type": "array_sorting",
  "knowledge": {
    "patterns": ["use_divide_and_conquer"],
    "insights": ["quicksort achieves O(n log n)"],
    "successful_approaches": ["quicksort", "mergesort"],
    "failed_approaches": ["insertion_sort", "selection_sort", "bubble_sort"]
  }
}
```

### 6.2 Retrieve Memory

**GET** `/api/memory/retrieve?task_type=array_sorting&limit=3`

Response:
```json
{
  "memories": [
    {
      "memory_id": "memory-uuid",
      "source_execution_id": "agent1-execution-uuid",
      "task_type": "array_sorting",
      "knowledge": {
        "patterns": ["use_divide_and_conquer"],
        "insights": ["quicksort achieves O(n log n)"],
        "successful_approaches": ["quicksort", "mergesort"],
        "failed_approaches": ["insertion_sort"]
      },
      "score_improvement": 20,
      "stored_at": "2026-10-30T12:00:00Z"
    }
  ]
}
```

### 6.3 Run Comparison Experiment

**POST** `/api/experiments/compare`

Request:
```json
{
  "task_description": "Implement a function to sort an array of integers in ascending order using an efficient algorithm.",
  "task_type": "array_sorting",
  "run_baseline": true,
  "run_with_memory": true
}
```

Response:
```json
{
  "experiment_id": "experiment-uuid",
  "baseline": {
    "execution_id": "baseline-execution-uuid",
    "v1_score": 72,
    "v2_score": 82,
    "total_improvement": 10
  },
  "with_memory": {
    "execution_id": "memory-execution-uuid",
    "memory_used": {
      "memory_id": "memory-uuid",
      "source_execution_id": "agent1-execution-uuid",
      "patterns_applied": ["use_divide_and_conquer"]
    },
    "v1_score": 86,
    "v2_score": 90,
    "total_improvement": 4,
    "v1_improvement_vs_baseline": 14
  }
}
```

---

## 7. Memory Lineage Tracking

Every execution with inherited knowledge records:

```json
{
  "execution_id": "agent2-memory-execution-uuid",
  "memory_lineage": {
    "source_execution_id": "agent1-execution-uuid",
    "memory_id": "memory-uuid",
    "patterns_applied": ["use_divide_and_conquer"],
    "insights_used": ["quicksort achieves O(n log n)"]
  },
  "evaluation": {
    "v1_score": 86,
    "v2_score": 90,
    "test_pass_rate": 100,
    "correctness": 90,
    "code_quality": 75
  },
  "comparison": {
    "baseline_v1": 72,
    "with_memory_v1": 86,
    "improvement": 14
  }
}
```

---

## 8. Demonstration Sequence

For the hackathon demo:

1. **Start:** Show Agent 1 executing sorting task
2. **Evolution:** V1 (68) → V2 (88), +20 improvement
3. **Memory:** Show memory stored in database
4. **Baseline:** Run Agent 2 WITHOUT memory, V1 (72), V2 (82), +10
5. **With Memory:** Run Agent 2 WITH memory, V1 (86), +14 vs baseline
6. **Comparison:** Side-by-side dashboard showing:
   - Baseline: 72 → 82 (+10)
   - With Memory: 86 → 90 (+14, starts higher)

---

## 9. Success Criteria

| Criterion | Definition |
|-----------|------------|
| Memory stored | Agent 1's execution creates memory record |
| Memory retrieved | Agent 2 queries and receives relevant memory |
| Pattern applied | Agent 2's generation prompt includes learned pattern |
| V1 score improvement | With-memory V1 > baseline V1 |
| Lineage recorded | Execution references source memory |

---

## 10. Limitations

1. **Single comparison** — Not statistically significant
2. **Same task** — May not generalize to different tasks
3. **Attribution** — Hard to isolate memory from other factors
4. **Task difficulty** — Even "same" tasks may have variation
5. **Model randomness** — Different runs may produce different results

---

**End of Cross-Agent Experiment Design v2.0**