# AutoEvolve Protocol — Architecture Documentation

**Version:** 1.0  
**Date:** October 30, 2026

---

## 1. Component Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Streamlit Dashboard                            │  │
│  │   - Command Center   - Evolution Lab   - Performance Analytics        │  │
│  │   - ZK Proof Center  - IPFS View       - Blockchain Explorer          │  │
│  │   - Agent Comparison                                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────┬────────────────────────────────────┘
                                         │ HTTP/REST (port 8000)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY LAYER                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           FastAPI Backend                              │  │
│  │   - Input validation        - Authentication          - Rate limiting │  │
│  │   - Request routing         - Response formatting     - Error handling│  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────┬────────────────────────────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         │                               │                               │
         ▼                               ▼                               ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  AGENT ORCHESTRATION│    │   ZK PROOF SERVICE  │    │  STORAGE SERVICES   │
│        LAYER        │    │                     │    │                     │
│                     │    │  ┌───────────────┐  │    │  ┌───────────────┐  │
│  ┌───────────────┐  │    │  │   Circom      │  │    │  │   SQLite      │  │
│  │ Orchestrator  │  │    │  │   Circuit     │  │    │  │   Database    │  │
│  │               │  │    │  └───────┬───────┘  │    │  └───────┬───────┘  │
│  │ - Task queue  │  │    │          │          │    │          │          │
│  │ - State machine│    │  ┌─────────▼─────────┐ │    │  ┌─────────▼─────────┐ │
│  │ - Workflow    │  │    │  │   snarkjs       │ │    │  │   IPFS/Pinata    │ │
│  └───────┬───────┘  │    │  │   Proof Gen/    │ │    │  │   Service        │ │
│          │          │    │  │   Verify        │ │    │  └─────────┬─────────┘ │
│  ┌───────▼───────┐  │    │  └─────────┬─────────┘ │    │            │          │
│  │  Generator    │  │    │            │           │    │  ┌─────────▼─────────┐ │
│  │  Agent        │  │    │  ┌─────────▼─────────┐ │    │  │  Blockchain       │ │
│  │               │  │    │  │  ZK Service API  │ │    │  │  Registry         │ │
│  │  - Code gen   │  │    │  └──────────────────┘ │    │  │  (Sepolia)        │ │
│  │  - Versioning │  │    └───────────────────────┘    │  └──────────────────┘ │
│  └───────┬───────┘  │                                  └──────────────────────┘
│          │          │
│  ┌───────▼───────┐  │
│  │  Critic       │  │
│  │  Agent        │  │
│  │               │  │
│  │  - Analysis   │  │
│  │  - Suggestions│  │
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │  Evaluator    │  │
│  │               │  │
│  │  - Deterministic│
│  │  - Metrics    │  │
│  └───────────────┘  │
└─────────────────────┘
```

---

## 2. Component Responsibilities

### 2.1 Dashboard Layer (Streamlit)

| Responsibility | Description |
|----------------|-------------|
| **UI Rendering** | Display all pages with Streamlit components |
| **User Input** | Accept task submissions, filter parameters |
| **Data Visualization** | Render Plotly charts, Pandas DataFrames |
| **API Communication** | All data via FastAPI HTTP endpoints |
| **No Direct Integration** | Never calls AI, IPFS, or Blockchain directly |

### 2.2 REST API Layer (FastAPI)

| Endpoint Category | Endpoints | Purpose |
|-------------------|-----------|---------|
| Task Management | POST/GET `/api/tasks` | Submit and retrieve tasks |
| Execution Control | GET `/api/executions` | List and view executions |
| Version History | GET `/api/versions` | Retrieve version details |
| ZK Operations | POST `/api/zk-proofs/*` | Generate and verify proofs |
| Storage | POST `/api/ipfs/*` | IPFS publication |
| Blockchain | POST `/api/blockchain/*` | On-chain registration |
| Memory | GET/POST `/api/memory` | Cross-agent knowledge |

### 2.3 Agent Orchestration Layer

#### Orchestrator Service
- **State Machine**: Manages execution states (see section 10 for the implemented lifecycle: `queued → generating_v1 → evaluating_v1 → critiquing → generating_v2 → evaluating_v2 → [generating_v3 → evaluating_v3] → zk_proof → ipfs_publish → blockchain_register → completed`, plus the terminal outcomes `completed_no_improvement`, `failed` and `cancelled`). Only the state table and persistence exist so far; the orchestrator that drives it is a later milestone.
- **Workflow Coordination**: Sequentially triggers Generator → Evaluator → Critic → Generator
- **Error Recovery**: Retries failed steps, rolls back on critical failures
- **Version Tracking**: Maintains V1, V2, V3 progression

#### Generator Agent
- **Input**: Task description, optional context from Critic
- **Output**: Code solution as string
- **API Integration**: Calls Featherless API (generator model)
- **Versioning**: Each generation tagged with version number

#### Critic Agent
- **Input**: Generated code, evaluation scores, task requirements
- **Output**: Structured critique with improvement recommendations
- **API Integration**: Calls Featherless API (critic model)
- **Format**: Actionable feedback for next generation

#### Evaluator Engine
- **Deterministic Metrics**:
  - Syntax correctness
  - Execution correctness (test cases)
  - Time complexity analysis
  - Space complexity analysis
  - Code quality (linting)
- **Scoring**: Normalized 0-100 score per metric, weighted total

### 2.4 ZK Proof Service

| Function | Description |
|----------|-------------|
| **Circuit Compilation** | Compile Circom circuit to R1CS |
| **Trusted Setup** | Generate proving/verification keys |
| **Proof Generation** | Create ZK proof from scores |
| **Proof Verification** | Verify proof correctness |
| **Public Signals** | Extract and store verifiable data |

### 2.5 Storage Services

#### SQLite Database
- **Tasks**: Task descriptions, creation time, status
- **Executions**: Execution metadata, timestamps
- **Versions**: Generated code, evaluation scores
- **Critiques**: AI feedback text
- **ZK Proofs**: Proof artifacts, verification status
- **Memory**: Cross-agent knowledge blobs

#### IPFS Service (Pinata)
- **Publication**: Upload execution JSON to IPFS
- **Retrieval**: Fetch execution by CID
- **Format**: JSON with full execution history

#### Blockchain Registry
- **Smart Contract**: AutoEvolveRegistry on Sepolia
- **Registration**: Store IPFS CID with execution metadata
- **Retrieval**: Query past registrations
- **Events**: Emit execution registered events

---

## 3. Data Flow

### 3.1 Primary Workflow

```
┌────────────┐
│  Developer │
│  Submits   │
│   Task     │
└─────┬──────┘
      │ POST /api/tasks
      ▼
┌──────────────────────────────────────────────────────────────────────┐
│                           FASTAPI LAYER                               │
│  - Validate request                                                   │
│  - Create task record in SQLite                                      │
│  - Return task_id                                                    │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼ (async event)
┌──────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR SERVICE                          │
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │
│  │  GENERATOR  │───▶│  EVALUATOR  │───▶│      CRITIC            │  │
│  │   (V1)      │    │    (V1)     │    │      (V1 feedback)     │  │
│  └─────────────┘    └─────────────┘    └───────────┬─────────────┘  │
│                                                      │                │
│                                                      ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │
│  │  GENERATOR  │───▶│  EVALUATOR  │───▶│   CHECK IMPROVEMENT    │  │
│  │   (V2)      │    │    (V2)     │    │   (score_v2 > score_v1)│  │
│  └─────────────┘    └─────────────┘    └───────────┬─────────────┘  │
│                                                      │                │
│                                           [Optional V3 iteration]    │
│                                                      │                │
└──────────────────────────────────────────────────────┼────────────────┘
                                                       │
                                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                           ZK PROOF SERVICE                            │
│  - Prepare public/private inputs                                     │
│  - Generate ZK proof (Circom + snarkjs)                              │
│  - Verify proof                                                       │
│  - Store proof artifacts                                             │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        STORAGE SERVICES                               │
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │    IPFS      │    │   SQLite     │    │    BLOCKCHAIN       │   │
│  │  (Pinata)    │    │  (Database)  │    │    (Sepolia)        │   │
│  │              │    │              │    │                      │   │
│  │ - Publish    │    │ - Store all  │    │ - Register CID      │   │
│  │   execution  │    │   records    │    │ - Emit event        │   │
│  │ - Return CID │    │              │    │                      │   │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      CROSS-AGENT MEMORY                               │
│                                                                      │
│  Store: Task type, learned patterns, successful strategies          │
│  Query: Retrieve relevant memory for new task                       │
│  Apply: Agent 2 uses memory in generation                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 API-to-Service Communication

```
Dashboard (Streamlit)
        │
        │ HTTP GET/POST
        ▼
FastAPI Routes
        │
        │ Internal function calls
        ▼
┌───────────────┐
│   Services    │
│               │
│ orchestrator  │◄──────┐
│ generator     │       │
│ critic        │       │ Shared database
│ evaluator     │       │ and state
│ zk_service    │       │
│ ipfs_service  │       │
│ blockchain    │       │
│ memory_service│       │
└───────────────┘       │
        │               │
        │ Returns       │
        ▼               │
FastAPI Response        │
        │               │
        ▼               │
Dashboard UI ◄──────────┘
```

---

## 4. API and Service Boundaries

### 4.1 Strict Boundaries

| Component | Can Access | Cannot Access |
|-----------|------------|---------------|
| Dashboard | FastAPI endpoints | Direct database, AI APIs, IPFS, Blockchain |
| FastAPI | All services | N/A |
| Generator | Featherless API, database | Directly: IPFS, Blockchain |
| Critic | Featherless API, database | Directly: IPFS, Blockchain |
| Evaluator | Test execution, database | External APIs |
| ZK Service | snarkjs, circom output | AI APIs |
| IPFS Service | Pinata API | AI APIs, Blockchain |
| Blockchain Service | Ethereum RPC | AI APIs |
| Memory Service | Database | External APIs |

### 4.2 Data Ownership

| Data Type | Owner Service | Access Pattern |
|-----------|--------------|----------------|
| Task records | Task API | Read/Write |
| Execution state | Orchestrator | Write, Read |
| Generated code | Generator | Write, Read |
| Evaluation scores | Evaluator | Write, Read |
| ZK proofs | ZK Service | Write, Read |
| IPFS CIDs | IPFS Service | Write |
| Blockchain Txs | Blockchain Service | Write |
| Memory blobs | Memory Service | Read/Write |

---

## 5. Agent Workflow

### 5.1 Agent 1 (Primary Evolution)

```
START: Task received
  │
  ▼
Generate V1 ──▶ Call Featherless (generator) ──▶ Store V1 code
  │
  ▼
Evaluate V1 ──▶ Run deterministic tests ──▶ Calculate scores
  │
  ▼
Critique V1 ──▶ Call Featherless (critic) ──▶ Store feedback
  │
  ▼
Generate V2 ──▶ Pass V1 + critique to Featherless ──▶ Store V2 code
  │
  ▼
Evaluate V2 ──▶ Run deterministic tests ──▶ Calculate scores
  │
  ▼
Compare V1/V2 ──▶ Check improvement (score_v2 > score_v1 + δ)
  │
  ▼
[Optional V3 if improvement < threshold]
  │
  ▼
ZK Proof ──▶ Generate proof of improvement
  │
  ▼
IPFS ──▶ Publish full execution snapshot
  │
  ▼
Blockchain ──▶ Register CID on Sepolia
  │
  ▼
Store Memory ──▶ Save learned patterns to database
  │
END
```

### 5.2 Agent 2 (Knowledge Inheritance)

```
START: New task received
  │
  ▼
Retrieve Memory ──▶ Query similar task types
  │
  ▼
Extract Knowledge ──▶ Get successful patterns, strategies
  │
  ▼
Baseline Check ──▶ Note: This is execution WITH memory
  │
  ▼
Generate Solution ──▶ Include memory context in prompt
  │
  ▼
Evaluate ──▶ Calculate scores
  │
  ▼
Compare with Baseline ──▶ Did memory help?
  │
  ▼
Store NEW Memory ──▶ Add to knowledge base
  │
END
```

---

## 6. Cross-Agent Memory Workflow

### 6.1 Memory Storage

```python
# What gets stored
memory_record = {
    "task_type": "sorting_algorithm",
    "pattern": "use_divide_and_conquer",
    "insights": [
        "quicksort outperforms bubble sort for large inputs",
        "consider space complexity alongside time"
    ],
    "successful_approaches": ["quicksort", "mergesort"],
    "failed_approaches": ["bubble_sort"],
    "source_execution_id": "uuid-v4"
}
```

### 6.2 Memory Retrieval

```python
# Query pattern
similar_memories = memory_service.retrieve(
    task_type="efficient_sorting",
    limit=5
)

# Agent 2 uses retrieved knowledge in generation prompt
prompt = f"""
Task: {task_description}

Relevant patterns from previous executions:
{format_memories(similar_memories)}

Generate a solution applying these insights.
"""
```

### 6.3 Knowledge Attribution

Each execution with inherited knowledge records:
- Source execution ID
- Memory entries used
- Whether knowledge improved outcome

---

## 7. Error Handling Strategy

### 7.1 Error Types

| Error Type | Handling | Example |
|------------|----------|---------|
| Transient | Retry with backoff | Network timeout |
| Validation | Return 422 (`VALIDATION_ERROR`) | Invalid input |
| Not Found | Return 404 | Unknown execution ID |
| External API | Return 503 | AI API failure |
| Critical | Rollback + alert | Blockchain transaction fails |

### 7.2 Recovery Patterns

```
External API Failure
        │
        ▼
┌───────────────┐
│  Retry 3x     │
│  (exponential)│
└───────┬───────┘
        │
   ┌────▼────┐
   │ Success │──▶ Continue workflow
   └────┬────┘
        │
   ┌────▼────┐
   │ Failed  │──▶ Store error state ──▶ Return 503 to client
   └─────────┘

Blockchain Failure
        │
        ▼
┌───────────────┐
│  Rollback     │
│  IPFS and DB  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  Store error  │──▶ Alert dashboard
│  Notify user  │
└───────────────┘
```

---

## 8. Security Architecture

### 8.1 Secret Management

```
┌─────────────────────────────────────┐
│        Environment Variables        │
│                                     │
│  FEATHERLESS_API_KEY                │
│  PINATA_API_KEY / SECRET            │
│  PRIVATE_KEY                        │
│  SEPOLIA_RPC_URL                    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│       Service Layer                 │
│  (reads os.environ.get)             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│    External Services                │
│  - Featherless API                  │
│  - Pinata                           │
│  - Ethereum RPC                     │
└─────────────────────────────────────┘
```

### 8.2 No Secret Storage

- ❌ Never store in database
- ❌ Never commit to git
- ❌ Never log
- ❌ Never display in UI

---

## 9. Scalability Considerations

### 9.1 Current Limits

| Resource | Limit | Rationale |
|----------|-------|-----------|
| Concurrent Executions | 10 | Database locking |
| Code Size | 100KB | API limits |
| History Versions | 10 per execution | Storage |

### 9.2 Future Optimizations

- Redis for execution state cache
- Message queue (Celery/RQ) for long-running tasks
- Separate read replicas for dashboard queries

---

**End of Architecture Documentation**


---

## 10. Implemented Backend Foundation (Milestone 05)

This section describes what exists today. Everything else in this document is still design.

### 10.1 What is implemented

- FastAPI application (`backend/app`) with SQLite persistence through SQLAlchemy 2, created by an app factory and configured through environment variables.
- Entities: `tasks`, `executions`, `execution_transitions` (append-only status history), `versions`, `evaluations`, `evaluation_operational_metrics`, `critic_feedback`, `agent_memories`.
- A validated execution lifecycle with timestamps and preserved failure information.
- Read endpoints for tasks, executions, versions, evaluations and Critic feedback, plus task and execution creation and execution cancellation. See `docs/API_CONTRACT.md`.

### 10.2 What is not implemented

No Featherless calls, Generator/Critic orchestration, revision engine, evaluation execution, ZK proof generation, IPFS, Pinata, blockchain, Streamlit dashboard, or cross-agent memory retrieval. No component moves an execution beyond `queued`. Creating an execution only records a queued row.

### 10.3 Lifecycle

```
queued -> generating_v1 -> evaluating_v1 -> critiquing -> generating_v2 -> evaluating_v2
       -> [generating_v3 -> evaluating_v3] -> zk_proof -> ipfs_publish -> blockchain_register -> completed
```

- `failed` and `cancelled` are reachable from every non-terminal state. `completed`, `completed_no_improvement`, `failed` and `cancelled` are terminal.
- `completed_no_improvement` means every permitted revision was evaluated and none was accepted. It is reachable only from `evaluating_v2` (when the execution permits a single revision, `max_revisions = 1`) and `evaluating_v3`, and only when each permitted revision is recorded, evaluated and rejected. It is not a failure, carries no error information, and has no outgoing transitions.
- Any other transition is rejected (HTTP 409 `INVALID_TRANSITION` through the API, `InvalidTransitionError` in code).
- Each transition is applied with a compare-and-swap `UPDATE`, so two racing transitions cannot both succeed, and is recorded in `execution_transitions` with its timestamp.
- Failure stores `error_code`, `error_message` and `error_stage` (the status it failed from). The database requires these fields exactly when the status is `failed`.

### 10.4 Trust boundaries in the data model

- Versions, evaluations and Critic feedback have no public write endpoint, so an API client cannot submit a score or a result. Only backend components write them, through the service layer.
- The overall deterministic score is computed from the components with the approved weights (test pass rate 50%, correctness 30%, code quality 20%, all on a 0-100 scale, no rounding). The database enforces this itself: CHECK constraints reject any evaluation whose stored pass rate or overall score differs from the recomputed value by more than 1e-9, so even a direct database write cannot store an inconsistent aggregate. The tolerance exists because bit-exact equality between Python and SQLite floating point is not guaranteed.
- Operational measurements (time, tokens, cost) live in a separate table and never enter the deterministic score. A cost figure always records whether it is `provider_reported` or `estimated`.
- Critic feedback is stored apart from evaluations. Its self-reported confidence is stored for the record and is not an improvement metric.
- The evaluator-led revision acceptance rule is not implemented yet. `Version.acceptance_status` (`pending`, `accepted`, `rejected`) and the rejection reason exist so that a later revision engine can record its decision.

### 10.5 No-improvement outcome and remaining gaps

**Resolved (Milestone 05.1):** an execution in which no revision improves the solution now has an honest terminal outcome, `completed_no_improvement`, instead of being forced into `failed`, `cancelled` or the proof stage. See section 10.3.

**Still open:** the lifecycle table still allows `evaluating_v2` or `evaluating_v3` to move to `zk_proof` regardless of whether any revision was accepted. Nothing yet stops a backend component from entering the proof stage without an accepted improvement. That check belongs to the revision engine, which is not implemented. The engine must enforce the approved acceptance rule: every test passed by the previous accepted version still passes, no deterministic dimension regresses, and the overall score strictly increases; otherwise the revision is rejected and the previous best version is kept.