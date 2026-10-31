# AutoEvolve Protocol — Dashboard Specification

**Version:** 1.0  
**Date:** October 30, 2026

> **Superseded.** The PRD specifies a **React web app** with seven screens: Home, New Task, Run View, Compare View, Capabilities, Memory and Trust, Verification. Use the PRD's Section 10 for the workflow. This Streamlit design is kept only for its page content. Rules that still apply: the dashboard calls FastAPI over HTTP only; it shows hidden tests as aggregate counts and never their names, contents or per-test results; it shows the exact failed term of a rejected revision; and it labels any sample data `SAMPLE DATA`. The backend fields it needs are in `docs/API_CONTRACT.md` (`/evaluations`, `/acceptance-decision`, `/evidence`). No dashboard exists yet.

---

## 1. Overview

The AutoEvolve Protocol dashboard is built with Streamlit and provides a comprehensive interface for visualizing the autonomous agent workflow. The dashboard communicates **exclusively** with the FastAPI backend — it does not implement agent orchestration, AI API calls, IPFS uploads, or blockchain transactions directly.

---

## 2. Design System

### 2.1 Color Palette

| Role | Color | Hex Code |
|------|-------|----------|
| Background (Primary) | Deep Charcoal | `#0D1117` |
| Background (Secondary) | Dark Slate | `#161B22` |
| Background (Tertiary) | Muted Gray | `#21262D` |
| Text (Primary) | Off-White | `#E6EDF3` |
| Text (Secondary) | Muted Gray | `#8B949E` |
| Accent (Primary) | Emerald | `#238636` |
| Accent (Secondary) | Lime | `#3FB950` |
| Accent (Tertiary) | Teal | `#58A6FF` |
| Error | Coral Red | `#F85149` |
| Warning | Amber | `#D29922` |
| Success | Bright Green | `#3FB950` |
| Border | Subtle Gray | `#30363D` |

### 2.2 Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Page Title | Inter | 28px | 700 |
| Section Header | Inter | 20px | 600 |
| Subsection | Inter | 16px | 600 |
| Body Text | Inter | 14px | 400 |
| Code | JetBrains Mono | 13px | 400 |
| Caption | Inter | 12px | 400 |
| Metric Value | Inter | 32px | 700 |

### 2.3 Component Styling

- **Cards**: Rounded corners (8px), subtle border (`#30363D`), slight shadow
- **Buttons**: Emerald background, white text, hover brightens
- **Inputs**: Dark background, light border, focus ring in teal
- **Charts**: Dark theme with emerald/lime/teal color series
- **Tables**: Striped rows, hover highlight

---

## 3. Page Structure

### 3.1 Navigation

```
┌─────────────────────────────────────────────────────────────┐
│                    SIDEBAR (Navigation)                      │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   🏠 Home       │                                         │
│  │   Command       │                                         │
│  │   Center        │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   🧬 Evolution  │                                         │
│  │   Lab           │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   📊 Analytics  │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   🔐 ZK         │                                         │
│  │   Proof Center  │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   🌐 IPFS       │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ⌐═══════════════                                             │
│  │   ⛓ Blockchain │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ┌─────────────────┐                                         │
│  │   🤖 Agent      │                                         │
│  │   Comparison    │                                         │
│  └─────────────────┘                                         │
│                                                              │
│  ──────────────────                                          │
│  Settings                                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Page Specifications

### 4.1 Page 1: Command Center (Home)

**Purpose**: Overview dashboard and quick actions

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Status Banner** | `/api/status` | Shows health of all services |
| **Quick Stats** | `/api/executions` | Total executions, success rate, avg improvement |
| **Recent Executions** | `/api/executions?limit=5` | Table of recent runs |
| **New Task Form** | POST `/api/tasks` | Form to submit new task |
| **Active Task Progress** | `/api/executions?status=running` | Progress bars for running tasks |

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  COMMAND CENTER                              [AutoEvolve]    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │   12         │ │    85%       │ │   +18        │         │
│  │  Executions  │ │ Success Rate │ │ Avg Improve  │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SERVICE STATUS                                       │   │
│  │  ✓ API        ✓ Database    ✓ Featherless            │   │
│  │  ✓ Pinata     ✓ Sepolia     ✓ ZK Circuit             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SUBMIT NEW TASK                                      │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ Task description...                            │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  │  [SUBMIT TASK]                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  RECENT EXECUTIONS                                    │   │
│  │  ID          Task        Status    Improvement        │   │
│  │  abc123...  Sorting     ✓ Done    +22                │   │
│  │  def456...  Search      ✓ Done    +15                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.2 Page 2: Evolution Lab

**Purpose**: View detailed execution evolution with all versions

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Execution Selector** | `/api/executions` | Dropdown to select execution |
| **Version Cards** | `/api/executions/{id}` | V1, V2, V3 cards with code |
| **Score Comparison** | Same as above | Bar chart comparing scores |
| **Critique Display** | Same as above | Show critic feedback per version |

**Mandatory Display Requirements:**

1. ✅ **Submitted task** — Full task description from execution
2. ✅ **Generated versions V1, V2, V3** — Each version's code displayed
3. ✅ **Test pass rate and score graph** — Bar/line chart showing scores per version

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  EVOLUTION LAB                              [Execution: xyz] │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SELECT EXECUTION: [▼ Select execution...                ]  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  TASK                                                │   │
│  │  "Implement an efficient sorting algorithm"          │   │
│  │  Criteria: O(n log n), handles edge cases            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌────────────────────────┐  ┌────────────────────────┐     │
│  │     VERSION V1         │  │     VERSION V2         │     │
│  │  Score: 65             │  │  Score: 87             │     │
│  │  ┌──────────────────┐  │  │  ┌──────────────────┐  │     │
│  │  │ code display     │  │  │  │ code display     │  │     │
│  │  │ (scrollable)     │  │  │  │ (scrollable)     │  │     │
│  │  └──────────────────┘  │  │  └──────────────────┘  │     │
│  │  [Copy Code]           │  │  [Copy Code]           │     │
│  └────────────────────────┘  └────────────────────────┘     │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SCORE COMPARISON                                     │   │
│  │                                                        │   │
│  │  V1 ████████████░░░░░░░░░░░░░ 65                      │   │
│  │  V2 ████████████████████████░ 87 (+22)                │   │
│  │                                                        │   │
│  │  Correctness:  80 → 100                               │   │
│  │  Efficiency:   50 → 85                                │   │
│  │  Readability: 65 → 75                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  CRITIC FEEDBACK (V1 → V2)                           │   │
│  │  "Consider using divide-and-conquer approach..."     │   │
│  │  Recommendations:                                     │   │
│  │  • Use quicksort or mergesort                         │   │
│  │  • Consider in-place modification                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.3 Page 3: Performance Analytics

**Purpose**: Aggregated analytics and trends

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Metrics Overview** | `/api/executions` | Avg scores, improvement distribution |
| **Improvement Histogram** | Same | Distribution of improvement values |
| **Task Type Analysis** | Same | Performance by task category |
| **Timeline Chart** | Same | Executions over time |

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  PERFORMANCE ANALYTICS                                       │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ Avg V1 Score │ │ Avg V2 Score │ │ Avg Improve  │         │
│  │    68        │ │    84        │ │    +16       │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  IMPROVEMENT DISTRIBUTION                             │   │
│  │       ▂▃▅▇▇▇▇▅▃▂                                      │   │
│  │  +0-5 +5-10 +10-15 +15-20 +20-25 +25+                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  EXECUTIONS OVER TIME                                 │   │
│  │                                                        │   │
│  │  █        █  █                                        │   │
│  │  █  █     █  █  █                                     │   │
│  │  █  █  █  █  █  █  █  █                              │   │
│  │  ──────────────────────                               │   │
│  │  Mon  Tue  Wed  Thu  Fri  Sat                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.4 Page 4: ZK Proof Center

**Purpose**: View and verify zero-knowledge proofs

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Proof Selector** | `/api/zk-proofs` | Select proof to view |
| **Proof Details** | `/api/zk-proofs/{id}` | Public signals, verification status |
| **Verification Status** | POST `/api/zk-proofs/verify` | Shows if proof verified |
| **Proof Artifact** | Same | Display proof metadata |

**Mandatory Display Requirements:**

4. ✅ **ZK proof generation and verification status** — Shows proof ID, status, verification result

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  ZK PROOF CENTER                                             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SELECT PROOF: [▼ Select proof...                         ] │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PROOF DETAILS                                        │   │
│  │                                                       │   │
│  │  Proof ID:    abc123-def456...                       │   │
│  │  Execution:   xyz789                                  │   │
│  │  Status:      ✓ Verified                              │   │
│  │  Generated:   2026-10-30 12:04:35                     │   │
│  │                                                       │   │
│  │  ─────────────────────────────────────────────────   │   │
│  │                                                       │   │
│  │  PUBLIC SIGNALS:                                      │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │ score_v1:         65                         │    │   │
│  │  │ score_v2:         87                         │    │   │
│  │  │ improvement_delta: 22                        │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  │                                                       │   │
│  │  MATHEMATICAL CLAIM:                                  │   │
│  │  score_v2 (87) > score_v1 (65) + delta (20)          │   │
│  │  Result: 87 > 85 ✓ VERIFIED                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  [VERIFY PROOF]  [VIEW PROOF ARTIFACT]               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.5 Page 5: Decentralized Storage (IPFS)

**Purpose**: View IPFS storage status

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **IPFS Selector** | `/api/ipfs` or executions | Select execution to view IPFS |
| **CID Display** | `/api/executions/{id}` | IPFS CID with copy button |
| **Content Preview** | `/api/ipfs/{cid}` | JSON preview of stored data |
| **Upload Status** | POST `/api/ipfs/publish` | Shows upload progress |

**Mandatory Display Requirements:**

5. ✅ **IPFS CID and storage status** — Shows CID, upload time, content preview

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  DECENTRALIZED STORAGE (IPFS)                                │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SELECT EXECUTION: [▼ Select execution...                ] │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  IPFS PUBLICATION                                    │   │
│  │                                                       │   │
│  │  CID:  QmXyZ123456789abcdefghijklmnopqrstuvwxyz     │   │
│  │        [📋 Copy]                                      │   │
│  │                                                       │   │
│  │  Status:      ✓ Published                            │   │
│  │  Uploaded:    2026-10-30 12:04:45                    │   │
│  │  Size:        4.2 KB                                 │   │
│  │                                                       │   │
│  │  [View on IPFS] [Refresh Status]                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  STORED CONTENT PREVIEW                               │   │
│  │  ┌────────────────────────────────────────────────┐  │   │
│  │  │ {                                                │  │   │
│  │  │   "task": "sorting algorithm",                  │  │   │
│  │  │   "versions": [...],                            │  │   │
│  │  │   "zk_proof": {...},                            │  │   │
│  │  │   "timestamp": "2026-10-30T12:04:45Z"          │  │   │
│  │  │ }                                                │  │   │
│  │  └────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.6 Page 6: Blockchain Registry

**Purpose**: View Ethereum Sepolia registrations

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Registration Selector** | `/api/blockchain` | Select to view details |
| **Transaction Details** | `/api/blockchain/{id}` | Tx hash, block number |
| **On-Chain Data** | Same | Scores, CID, timestamp |
| **Event Log** | Same | Emission of registration event |

**Mandatory Display Requirements:**

6. ✅ **Blockchain transaction hash and emitted event** — Shows tx hash, block, event data

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  BLOCKCHAIN REGISTRY (Ethereum Sepolia)                      │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SELECT REGISTRATION: [▼ Select execution...              ] │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  TRANSACTION DETAILS                                  │   │
│  │                                                       │   │
│  │  Transaction Hash:                                    │   │
│  │  0xabc123def456789... [📋 Copy]                      │   │
│  │                                                       │   │
│  │  Block Number:  12,345,678                            │   │
│  │  Status:        ✓ Confirmed                           │   │
│  │  Gas Used:      45,231                                │   │
│  │  Confirmed:     2026-10-30 12:05:30                   │   │
│  │                                                       │   │
│  │  [View on Etherscan]                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ON-CHAIN DATA                                        │   │
│  │                                                       │   │
│  │  IPFS CID:       QmXyZ123...                         │   │
│  │  Task:           Sorting algorithm                   │   │
│  │  Score V1:       65                                  │   │
│  │  Score V2:       87                                  │   │
│  │  Improvement:    +22                                 │   │
│  │                                                       │   │
│  │  ─────────────────────────────────────────────────   │   │
│  │                                                       │   │
│  │  EMITTED EVENT:                                       │   │
│  │  ExecutionRegistered(                                │   │
│  │    executionId: 0xabc123...,                        │   │
│  │    ipfsCid: QmXyZ123...,                            │   │
│  │    timestamp: 1738166400                             │   │
│  │  )                                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.7 Page 7: Agent Comparison

**Purpose**: Compare Agent 1 (with evolution) vs Agent 2 (knowledge inheritance)

**Components:**

| Component | Data Source | Description |
|-----------|-------------|-------------|
| **Execution Pairs** | `/api/memory` + `/api/executions` | Link Agent 1 → Agent 2 |
| **Agent 1 Summary** | `/api/executions/{id}` | Original execution |
| **Agent 2 Summary** | `/api/executions/{id}` | With inherited knowledge |
| **Comparison Chart** | Both endpoints | Side-by-side metrics |

**Mandatory Display Requirements:**

7. ✅ **Agent 1 versus Agent 2 comparison** — Shows knowledge transfer, performance difference

**Layout:**
```
┌──────────────────────────────────────────────────────────────┐
│  AGENT COMPARISON (Knowledge Inheritance)                    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  SELECT COMPARISON:                                          │
│  [▼ Agent 1 execution → Agent 2 execution                  ] │
│                                                               │
│  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  │     AGENT 1             │  │     AGENT 2             │   │
│  │  (Original Evolution)   │  │  (With Memory)          │   │
│  │                         │  │                         │   │
│  │  Task: Sorting          │  │  Task: Search           │   │
│  │  Versions: V1 → V2      │  │  Versions: V1 → V2      │   │
│  │  Improvement: +22       │  │  Improvement: +28       │   │
│  │                         │  │  Memory Source: abc123  │   │
│  │                         │  │  (Inherited patterns)   │   │
│  └─────────────────────────┘  └─────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  PERFORMANCE COMPARISON                               │   │
│  │                                                       │   │
│  │  Score    ████████████████  Agent 1: 87              │   │
│  │           █████████████████ Agent 2: 93 (+6)          │   │
│  │                                                       │   │
│  │  Iterations: 2      →        Iterations: 1           │   │
│  │  Time: 4:30         →        Time: 2:15              │   │
│  │                                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  INHERITED KNOWLEDGE                                  │   │
│  │                                                       │   │
│  │  From Execution: abc123...                           │   │
│  │  Task Type: sorting_algorithm                         │   │
│  │                                                       │   │
│  │  Patterns Applied:                                    │   │
│  │  • use_divide_and_conquer                            │   │
│  │  • prefer_in_place                                   │   │
│  │                                                       │   │
│  │  Insights Used:                                       │   │
│  │  • "quicksort outperforms for large n"               │   │
│  │  • "consider space complexity"                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Code Diff Display

**Implementation**: Use `st.code` with diff view

For displaying code differences between versions:

```
┌─────────────────────────────────────────────────────────────┐
│  CODE DIFF: V1 → V2                                         │
├─────────────────────────────────────────────────────────────┤
│  - def bubble_sort(arr):                                    │
│  -     n = len(arr)                                         │
│  -     for i in range(n):                                   │
│  -         for j in range(0, n-i-1):                        │
│  -             if arr[j] > arr[j+1]:                        │
│  -                 arr[j], arr[j+1] = arr[j+1], arr[j]      │
│  + def quicksort(arr):                                       │
│  +     if len(arr) <= 1:                                    │
│  +         return arr                                        │
│  +     pivot = arr[len(arr) // 2]                           │
│  +     left = [x for x in arr if x < pivot]                 │
│  +     middle = [x for x in arr if x == pivot]              │
│  +     right = [x for x in arr if x > pivot]                │
│  +     return quicksort(left) + middle + quicksort(right)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Data Source Requirements

### 6.1 Every Displayed Metric Must Come From:

| Dashboard Display | Data Source | Endpoint |
|-------------------|-------------|----------|
| Task description | Execution detail | GET `/api/executions/{id}` |
| V1, V2, V3 code | Version detail | GET `/api/versions/{id}` |
| Scores | Version detail | GET `/api/versions/{id}` |
| Test pass rate | Version evaluation | GET `/api/versions/{id}/evaluate` |
| Score graph | Version data | GET `/api/executions/{id}/versions` |
| Code diff | Version code | GET `/api/versions/{id}` |
| Critic feedback | Version critique | GET `/api/versions/{id}` |
| ZK proof status | ZK proof detail | GET `/api/zk-proofs/{id}` |
| IPFS CID | Execution detail | GET `/api/executions/{id}` |
| Blockchain tx | Blockchain detail | GET `/api/blockchain/{id}` |
| Agent comparison | Memory + executions | GET `/api/memory/retrieve` |

### 6.2 Sample Data Labeling

If displaying sample/preview data during development:

```
┌─────────────────────────────────────┐
│  ⚠️  SAMPLE DATA — NOT REAL         │
│                                     │
│  This is preview data for          │
│  dashboard development only.       │
└─────────────────────────────────────┘
```

---

## 7. Error States

### 7.1 Service Unavailable

```
┌─────────────────────────────────────┐
│  ⚠️  SERVICE UNAVAILABLE             │
│                                     │
│  Pinata IPFS is not responding.    │
│  Some features may be limited.     │
│                                     │
│  [Retry Connection]                │
└─────────────────────────────────────┘
```

### 7.2 Loading States

```
┌─────────────────────────────────────┐
│  ⏳  Loading execution data...      │
│                                     │
│  Please wait...                     │
└─────────────────────────────────────┘
```

---

## 8. Implementation Checklist

All nine mandatory requirements:

- [x] 1. Submitted task
- [x] 2. Generated versions V1, V2, V3
- [x] 3. Test pass rate and score graph
- [x] 4. ZK proof generation and verification status
- [x] 5. IPFS CID and storage status
- [x] 6. Blockchain transaction hash and emitted event
- [x] 7. Agent 1 versus Agent 2 comparison

---

**End of Dashboard Specification**