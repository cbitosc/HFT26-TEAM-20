# AutoEvolve Protocol — Technical Specification

**Version:** 1.0  
**Status:** Draft  
**Date:** October 30, 2026

---

## 1. Project Overview

### 1.1 Objective

AutoEvolve Protocol is an autonomous agent framework that demonstrates measurable solution improvement, verifiable improvement claims through zero-knowledge proofs, and cross-agent knowledge inheritance.

The system proves that an AI agent can iteratively improve its output based on structured critique, with every improvement claim verifiable through cryptographic proof and immutable on-chain registration.

### 1.2 Core Workflow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Developer  │───▶│ FastAPI API  │───▶│ Orchestrator│
│  Submits    │    │  (REST API)  │    │  (Agent)    │
│  Task       │    └──────────────┘    └──────┬──────┘
└─────────────┘                              │
                                              ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Dashboard  │◀───│  Streamlit   │◀───│  Database   │
│  (View)     │    │  (UI Layer)  │    │  (SQLite)   │
└─────────────┘    └──────────────┘    └─────────────┘
```

### 1.3 Complete Execution Pipeline

1. **Task Submission** — Developer submits a coding task via API
2. **Initial Generation** — AI Generator produces solution V1
3. **Evaluation V1** — Deterministic Evaluator measures performance
4. **Critique V1** — AI Critic analyzes weaknesses
5. **Iteration V2** — Generator produces revised solution
6. **Evaluation V2** — Same evaluator measures V2
7. **Iteration V3** — Optional further improvements
8. **ZK Proof Generation** — Circom circuit proves improvement
9. **IPFS Publication** — Execution snapshot published to IPFS
10. **Blockchain Registration** — Smart contract records CID on Sepolia
11. **Knowledge Transfer** — Second agent retrieves and applies learned knowledge
12. **Dashboard Visualization** — Complete workflow displayed

---

## 2. Technology Stack

### 2.1 Mandatory Technologies

| Layer | Technology | Purpose |
|-------|------------|---------|
| Dashboard | Streamlit | Developer UI for workflow visualization |
| Data Processing | Pandas | Data manipulation and analysis |
| Visualizations | Plotly | Interactive charts for version comparison |
| Backend | Python + FastAPI | REST API and request handling |
| AI API | Featherless API | Generator and Critic model access |
| Agent Orchestration | Python | Workflow coordination |
| Evaluation | Deterministic Python | Performance measurement |
| Database | SQLite | Persistence layer |
| ZK Circuits | Circom | Circuit definition |
| ZK Proof System | snarkjs | Proof generation and verification |
| Smart Contracts | Solidity | On-chain registry |
| Contract Tooling | Foundry | Compilation and deployment |
| Blockchain | Ethereum Sepolia | Testnet deployment |
| Decentralized Storage | IPFS + Pinata | Immutable execution history |
| Version Control | Git / GitHub | Source code management |

### 2.2 Technology Boundaries

- **Dashboard ↔ Backend:** Streamlit communicates ONLY with FastAPI REST endpoints
- **Backend ↔ AI:** FastAPI manages all Featherless API calls
- **ZK Layer:** Circom generates circuits, snarkjs handles proof operations
- **Blockchain Layer:** All EVM interactions go through the Registry Service

---

## 3. Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DASHBOARD LAYER                                │
│                    (Streamlit + Pandas + Plotly)                        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP/REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            REST API LAYER                                │
│                      (FastAPI - Port 8000)                              │
│  /tasks, /executions, /versions, /zk-proofs, /ipfs, /blockchain        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ Internal Calls
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     AGENT ORCHESTRATION LAYER                           │
│                  (Orchestrator + Generator + Critic)                    │
│  - Task decomposition    - Solution generation   - Critique analysis   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Evaluation     │    │   ZK Proof      │    │   Storage       │
│  Engine         │    │   Service       │    │   Services      │
│                 │    │                 │    │                 │
│ - Deterministic │    │ - Circom        │    │ - IPFS/Pinata   │
│   metrics       │    │   circuits      │    │ - SQLite DB     │
│ - Version       │    │ - snarkjs       │    │ - Blockchain    │
│   comparison    │    │   proofs        │    │   Registry      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 3.2 Component Responsibilities

#### Dashboard Layer (Streamlit)

| Responsibility | Details |
|----------------|---------|
| **Visualization** | Display execution workflows, version comparisons, metrics charts |
| **User Interaction** | Task submission, execution history browsing, ZK proof viewing |
| **Data Display** | Render Pandas DataFrames, Plotly charts |
| **Communication** | HTTP calls to FastAPI only — no direct AI/ZK/Blockchain access |

#### REST API Layer (FastAPI)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tasks` | POST | Submit new task |
| `/tasks/{id}` | GET | Get task status |
| `/executions` | GET | List all executions |
| `/executions/{id}` | GET | Get execution details |
| `/versions/{execution_id}` | GET | Get all versions for an execution |
| `/versions/{id}/evaluate` | POST | Trigger evaluation for a version |
| `/zk-proofs` | GET | List ZK proofs |
| `/zk-proofs/generate` | POST | Generate ZK proof for improvement claim |
| `/ipfs/publish` | POST | Publish execution to IPFS |
| `/blockchain/register` | POST | Register CID on Sepolia |
| `/memory/retrieve` | GET | Retrieve cross-agent memory |
| `/memory/store` | POST | Store learned knowledge |

#### Agent Orchestration Layer

| Component | Responsibility |
|-----------|----------------|
| **Orchestrator** | Coordinate entire workflow, manage state machine, trigger components sequentially |
| **Generator Agent** | Produce code solutions using Featherless API (generator model) |
| **Critic Agent** | Analyze solutions, identify weaknesses, recommend improvements (Featherless API critic model) |

#### Evaluation Engine

**A. Deterministic (Reproducible - Same Input → Same Output):**

| Metric | Description | Scoring |
|--------|-------------|---------|
| **Test Pass Rate** | % of predefined test cases passed | 0-100 |
| **Correctness** | Compiles, syntax valid, basic validation | 0-100 |
| **Code Quality** | Cyclomatic complexity, lint score | 0-100 |

**B. Operational (Varies by Environment):**

| Metric | Description | Notes |
|--------|-------------|-------|
| **Execution Time** | Time to complete task | System-dependent |
| **Token Usage** | API tokens consumed | Varies by model |
| **Cost** | API cost in USD | Varies by pricing |

**Total Score Formula:**
```
total_score = (test_pass_rate * 0.5) + (correctness * 0.3) + (code_quality * 0.2)
```

**Note:** Same evaluation procedure applies to V1, V2, and V3.

#### Version History & Comparison

| Feature | Description |
|---------|-------------|
| **Version Storage** | Each version (V1, V2, V3) stored with full code, metrics, timestamp |
| **Diff View** | Side-by-side code comparison between versions |
| **Metric Trends** | Chart showing metric improvements across versions |

#### Cross-Agent Memory

| Feature | Description |
|---------|-------------|
| **Memory Store** | SQLite table storing learned patterns, successful strategies |
| **Retrieval** | Query memory by task type, retrieve relevant context |
| **Application** | Second agent incorporates retrieved knowledge into new task |

#### ZK Proof Service

| Component | Responsibility |
|-----------|----------------|
| **Circom Circuit** | Define improvement claim (e.g., "score V2 > score V1") |
| **Proof Generation** | Use snarkjs to generate zero-knowledge proof |
| **Proof Verification** | Verify proof without revealing underlying data |

**ZK Claim Structure:**
```
Input: 
  - score_v1: public
  - score_v2: public  
  - improvement_delta: public
  - hash_v1: private
  - hash_v2: private

Output:
  - proof: SNARK proof
  - public_signals: [score_v1, score_v2, improvement_delta]
```

#### IPFS Storage Service

| Feature | Description |
|---------|-------------|
| **Publisher** | Upload execution metadata to IPFS via Pinata |
| **Content** | JSON containing task, all versions, evaluations, critic feedback |
| **CID Return** | Return IPFS CID for on-chain registration |

#### Blockchain Registry Service

| Feature | Description |
|---------|-------------|
| **Smart Contract** | Solidity contract on Sepolia storing execution CIDs |
| **Registration** | Call contract to store IPFS CID with metadata |
| **Verification** | Read contract to verify past registrations |

#### SQLite Persistence Layer

| Table | Schema |
|-------|--------|
| `tasks` | id, description, created_at, status |
| `executions` | id, task_id, started_at, completed_at, ipfs_cid, tx_hash |
| `versions` | id, execution_id, version_number, code, evaluator_scores, created_at |
| `critiques` | id, version_id, critique_text, recommendations |
| `zk_proofs` | id, execution_id, proof_json, public_signals, verified |
| `memory` | id, task_type, knowledge_blob, created_at |

> **Status:** the table above is the original planned schema. The implemented schema (Milestone 05) lives in `backend/app/models` and differs: tables `tasks`, `executions`, `execution_transitions`, `versions`, `evaluations`, `evaluation_operational_metrics`, `critic_feedback` and `agent_memories`. `zk_proofs`, IPFS CID and transaction columns are **not yet implemented**.

### 3.3 Data Flow

```
Task Submission
      │
      ▼
┌─────────────────┐
│  FastAPI POST   │
│  /tasks         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Store Task     │◀──── SQLite (tasks table)
│  in Database    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Orchestrator   │
│  Triggers       │
│  Generator      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Generator      │────▶│  Featherless    │
│  (V1)           │     │  API (model)    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Store Version  │◀──── SQLite (versions table)
│  V1 in DB       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Evaluation     │
│  Engine         │
│  (V1 metrics)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Critic         │────▶│  Featherless    │
│  (feedback)     │     │  API (model)    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│  Generator      │
│  (V2 + feedback)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Evaluate V2    │
│  Compare V1/V2  │
└────────┬────────┘
         │
    [Optional V3]
         │
         ▼
┌─────────────────┐
│  ZK Proof       │
│  Service        │
│  (Circom+snark) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  IPFS Service   │
│  (Pinata)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Blockchain     │
│  Registry       │
│  (Sepolia)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Store Memory   │◀──── SQLite (memory table)
│  for future     │
│  agents         │
└─────────────────┘
```

---

## 4. ZK Proof Design (RANGE-CORRECTED)

### 4.1 Proof Scope

The ZK circuit proves:

> `score_v2 >= score_v1 + delta`

Where:
- `score_v1` is in range 0-100
- `score_v2` is in range 0-100
- `delta` is in range 1-50
- Equality at boundary MUST pass
- Smaller score MUST fail
- Invalid inputs MUST fail

### 4.2 Circuit Design (Range-Corrected)

**Public Inputs:**
| Input | Range | Bits |
|-------|-------|------|
| score_v1 | 0-100 | 7 |
| score_v2 | 0-100 | 7 |
| delta | 1-50 | 6 |

**Private Inputs:** None

**Circom Components (circomlib):**
- `Num2Bits(n)` — Bit decomposition
- `LessEqThan(n)` — Bounded comparison (a <= b)
- `GreaterThan(n)` — Comparison (a > b)

**Circuit Constraints:**
```circom
pragma circom 2.0.0;
include "circomlib/bitify.circom";
include "circomlib/comparators.circom";

template ImprovementProof() {
    signal input score_v1;  // 0-100
    signal input score_v2;  // 0-100
    signal input delta;     // 1-50

    // === score_v1: 0 <= score_v1 <= 100 ===
    component v1Bits = Num2Bits(7);
    v1Bits.in <== score_v1;
    
    component v1Le100 = LessEqThan(7);
    v1Le100.in[0] <== score_v1;
    v1Le100.in[1] <== 100;
    v1Le100.out === 1;

    // === score_v2: 0 <= score_v2 <= 100 ===
    component v2Bits = Num2Bits(7);
    v2Bits.in <== score_v2;
    
    component v2Le100 = LessEqThan(7);
    v2Le100.in[0] <== score_v2;
    v2Le100.in[1] <== 100;
    v2Le100.out === 1;

    // === delta: 1 <= delta <= 50 ===
    component deltaBits = Num2Bits(6);
    deltaBits.in <== delta;
    
    component deltaLe50 = LessEqThan(6);
    deltaLe50.in[0] <== delta;
    deltaLe50.in[1] <== 50;
    deltaLe50.out === 1;
    
    component deltaGt0 = GreaterThan(6);
    deltaGt0.in[0] <== delta;
    deltaGt0.in[1] <== 0;
    deltaGt0.out === 1;

    // === Main claim: target <= score_v2, i.e. score_v2 >= score_v1 + delta ===
    // A separate target <= 150 check is redundant given the ranges above and is omitted.
    signal target;
    target <== score_v1 + delta;

    component mainClaim = LessEqThan(8);
    mainClaim.in[0] <== target;
    mainClaim.in[1] <== score_v2;
    mainClaim.out === 1;
}

component main {public [score_v1, score_v2, delta]} = ImprovementProof();
```

**Implementation:** `zk/circuits/improvement_proof.circom` (circom 2.2.3, circomlib 2.0.5, snarkjs 0.7.6). Compiled to 82 constraints. Full constraint inventory, setup procedure and executed results are in `docs/ZK_TRUST_MODEL.md`.

### 4.3 Trust Model

| Aspect | Status |
|--------|--------|
| Mathematical claim | ✅ score_v2 >= score_v1 + delta |
| Equality at boundary | ✅ PASSES |
| Range constraints | ✅ Properly enforced |
| Code binding | ❌ NOT included |
| Evaluator honesty | ❌ Assumed trustworthy |

### 4.4 What CANNOT Be Proven

- Evaluator correctness or honesty
- Semantic quality of solution
- AI reasoning or intelligence
- Code correctness beyond numerical scores

### 4.5 Public Signals

```json
{
  "score_v1": 65,
  "score_v2": 75,
  "delta": 10
}
```

### 4.6 Test Cases (executed with `node zk/tests/run_tests.js`)

| Case | score_v1 | score_v2 | delta | Expected | Actual |
|------|----------|----------|-------|----------|--------|
| 1 | 65 | 82 | 10 | PASS | PASS (proof verified) |
| 2 | 65 | 75 | 10 | PASS | PASS (proof verified, equality) |
| 3 | 65 | 74 | 10 | FAIL | FAIL (witness rejected) |
| 4 | 82 | 65 | 10 | FAIL | FAIL (witness rejected) |
| 5 | 0 | 100 | 50 | PASS | PASS (proof verified) |
| 6 | 100 | 100 | 1 | FAIL | FAIL (witness rejected) |
| 7 | 65 | 150 | 10 | FAIL | FAIL (witness rejected) |
| 8 | 65 | 80 | 0 | FAIL | FAIL (witness rejected) |
| 9 | 65 | 80 | 51 | FAIL | FAIL (witness rejected) |
| 10 | -5 | 50 | 10 | FAIL | FAIL (witness rejected) |

Tampering: a verified proof for (65, 75, 10) was rejected when `public.json` was changed to (65, 82, 10) or (65, 75, 9).

The trusted setup is development-only (single party). See `docs/ZK_TRUST_MODEL.md` section 8.

---

## 5. API Contracts

> **Status:** the authoritative contract for the endpoints that exist today is `docs/API_CONTRACT.md`. The examples in this section are the original planned shapes and differ from the implementation (for example, creating a task does not start an execution, and resource identifiers are named `id`). Endpoints for ZK proofs, IPFS, blockchain and memory are **not yet implemented**.

### 5.1 Task Submission

**POST** `/api/tasks`

```json
Request:
{
  "description": "Write a function to reverse a linked list",
  "acceptance_criteria": ["O(n) time complexity", "handles empty list", "handles single node"],
  "evaluation_config": {
    "metrics": ["correctness", "efficiency", "readability"]
  }
}

Response:
{
  "task_id": "uuid-v4",
  "status": "queued",
  "created_at": "2026-10-30T12:00:00Z"
}
```

### 5.2 Execution Result

**GET** `/api/executions/{execution_id}`

```json
Response:
{
  "execution_id": "uuid-v4",
  "task_id": "uuid-v4",
  "versions": [
    {
      "version": "v1",
      "code": "...",
      "scores": {
        "correctness": 70,
        "efficiency": 60,
        "readability": 65
      },
      "total_score": 65,
      "critique": "..."
    },
    {
      "version": "v2",
      "code": "...",
      "scores": {
        "correctness": 90,
        "efficiency": 80,
        "readability": 75
      },
      "total_score": 82,
      "improvement": 17
    }
  ],
  "zk_proof": {
    "verified": true,
    "proof_cid": "Qm...",
    "public_signals": [65, 82, 17]
  },
  "ipfs_cid": "Qm...",
  "blockchain_tx": "0x..."
}
```

---

## 6. Smart Contract Specification

### 6.1 Contract: AutoEvolveRegistry (AUDITED)

**Location:** `contracts/AutoEvolveRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

// NOTE: This contract stores data but does NOT verify ZK proofs on-chain.
// All score values are trusted inputs from the backend.
// Trust Model: Backend provides accurate scores; contract provides immutability.

contract AutoEvolveRegistry {
    struct ExecutionRecord {
        string ipfsCid;           // IPFS content identifier
        uint256 scoreV1;          // V1 score (0-100)
        uint256 scoreV2;          // V2 score (0-100)
        uint256 improvementDelta; // scoreV2 - scoreV1
        uint256 timestamp;        // Registration time
        bool exists;              // Prevents duplicate registrations
    }
    
    // Mapping: execution_id -> record
    mapping(bytes32 => ExecutionRecord) public records;
    
    // List of all execution IDs for enumeration
    bytes32[] public executionIds;
    
    event ExecutionRegistered(
        bytes32 indexed executionId,
        string ipfsCid,
        uint256 timestamp
    );
    
    // NOTE: No task description stored - reduces on-chain data
    // NOTE: No access control - anyone can register (appropriate for testnet)
    // NOTE: Duplicate check prevents overwrites
    
    function registerExecution(
        bytes32 executionId,
        string memory ipfsCid,
        uint256 scoreV1,
        uint256 scoreV2,
        uint256 improvementDelta
    ) external {
        // Prevent duplicate registrations
        require(!records[executionId].exists, "Execution already registered");
        
        // Validate score ranges
        require(scoreV1 <= 100, "ScoreV1 too high");
        require(scoreV2 <= 100, "ScoreV2 too high");
        require(scoreV2 > scoreV1, "ScoreV2 must exceed scoreV1");
        
        records[executionId] = ExecutionRecord({
            ipfsCid: ipfsCid,
            scoreV1: scoreV1,
            scoreV2: scoreV2,
            improvementDelta: improvementDelta,
            timestamp: block.timestamp,
            exists: true
        });
        
        executionIds.push(executionId);
        
        emit ExecutionRegistered(executionId, ipfsCid, block.timestamp);
    }
    
    function getExecution(bytes32 executionId) 
        external 
        view 
        returns (ExecutionRecord memory) 
    {
        require(records[executionId].exists, "Execution not found");
        return records[executionId];
    }
    
    function getExecutionCount() external view returns (uint256) {
        return executionIds.length;
    }
    
    function isRegistered(bytes32 executionId) external view returns (bool) {
        return records[executionId].exists;
    }
}
```

### 6.2 Smart Contract Trust Model

| Aspect | Status |
|--------|--------|
| ZK Proof Verification | ❌ NOT on-chain (off-chain via snarkjs) |
| Score Accuracy | ❌ Assumed from backend |
| IPFS CID | ✅ Stored immutably |
| Timestamp | ✅ Block timestamp |
| Duplicate Prevention | ✅ `exists` flag check |

**Security Notes:**
- No access control (appropriate for public testnet)
- No task description stored (reduces data)
- Score validation prevents invalid values
- Duplicate check prevents overwrite attacks

---

## 7. File Structure

> **Status:** this tree is the *target* structure. Items marked `[implemented]` exist; the rest are `[planned]`.
> The implemented backend is a single `app` package (see `backend/README.md`), not the layout originally drawn here.
> There is no SQL schema file or migrations directory: the database is created by SQLAlchemy at startup.

```
CBIT/
├── SPEC.md, README.md, AGENTS.md          [implemented]
│
├── backend/                               [implemented, Milestones 05 and 05.1]
│   ├── app/
│   │   ├── main.py, config.py, database.py, init_db.py
│   │   ├── lifecycle.py, scoring.py, errors.py
│   │   ├── models/      (task, execution, version, evaluation, critic_feedback, agent_memory)
│   │   ├── schemas/
│   │   ├── services/    (task, execution, version)         [planned: orchestrator, generator, critic,
│   │   │                                                     evaluator, zk, ipfs, blockchain, memory]
│   │   └── api/routes/  (health, tasks, executions, versions)  [planned: zk_proofs, ipfs, blockchain]
│   ├── tests/
│   ├── requirements.txt, pytest.ini, .env.example, README.md
│
├── zk/                                    [implemented: standalone prototype]
│   ├── circuits/improvement_proof.circom
│   ├── scripts/build.js                   (compile + development-only trusted setup)
│   ├── tests/run_tests.js
│   └── package.json
│
├── eval/                                  [research tooling: Featherless harnesses and results]
├── docs/                                  [implemented]
│
├── dashboard/                             [planned] Streamlit app and API client
├── contracts/                             [planned] AutoEvolveRegistry.sol, Foundry project
└── tests/                                 [planned] cross-component integration tests
```

---

## 8. Environment Variables

Create `.env` file:

```env
# FastAPI
API_HOST=0.0.0.0
API_PORT=8000

# Featherless API
FEATHERLESS_API_KEY=your_api_key_here
FEATHERLESS_GENERATOR_MODEL=generator-model-name
FEATHERLESS_CRITIC_MODEL=critic-model-name

# IPFS/Pinata
PINATA_API_KEY=your_pinata_key
PINATA_API_SECRET=your_pinata_secret

# Ethereum Sepolia
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/your_project_id
PRIVATE_KEY=your_private_key_here
CONTRACT_ADDRESS=deployed_contract_address

# Database
DATABASE_URL=sqlite:///./autoevolve.db
```

> **Status:** the backend reads `APP_ENV`, `DATABASE_URL`, `FEATHERLESS_API_KEY`, `FEATHERLESS_BASE_URL`, `FEATHERLESS_GENERATOR_MODEL`, `FEATHERLESS_CRITIC_MODEL` and `API_TIMEOUT_SECONDS` from the environment or `backend/.env` (see `backend/.env.example`). The Pinata, Sepolia, `PRIVATE_KEY` and `CONTRACT_ADDRESS` variables are **planned**. `API_HOST` and `API_PORT` are not read; pass `--host` and `--port` to uvicorn. `DATABASE_URL` defaults to `backend/data/autoevolve.db`. No Critic model default exists because none is approved.

---

## 9. Development Rules

### 9.1 Architecture Boundaries

1. **Dashboard only communicates with FastAPI** — No direct database, AI, ZK, or blockchain access
2. **FastAPI owns all external communication** — IPFS, Ethereum, Featherless API
3. **Agent orchestration is stateless** — All state persisted in SQLite
4. **ZK proofs are isolated** — Circuit logic separate from application logic

### 9.2 Security Rules

1. **Never commit secrets** — Use `.env` files, add to `.gitignore`
2. **Validate all inputs** — Pydantic validation on all API endpoints
3. **Private keys never in code** — Use environment variables only
4. **ZK circuit inputs sanitized** — No raw user input to ZK circuits

### 9.3 Testing Requirements

1. **Unit tests for each service**
2. **Integration tests for API endpoints**
3. **ZK circuit tests with known inputs**
4. **Smart contract tests with Foundry**

---

## 10. Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Task submission creates execution record in SQLite | Database query |
| AC-2 | Generator produces valid code solution | Code syntax check |
| AC-3 | Evaluator returns deterministic scores | Repeated runs yield same scores |
| AC-4 | Critic provides actionable feedback | Feedback contains improvement suggestions |
| AC-5 | Version comparison shows metric differences | Dashboard visualization |
| AC-6 | ZK proof verifies improvement claim | snarkjs verification passes |
| AC-7 | IPFS returns valid CID | CID format validation |
| AC-8 | Blockchain transaction succeeds | Sepolia transaction confirmed |
| AC-9 | Second agent retrieves prior knowledge | Memory retrieval returns relevant data |
| AC-10 | Dashboard displays complete workflow | Streamlit UI renders all data |

---

## 11. Next Steps and Status

| # | Step | Status |
|---|------|--------|
| 1 | Environment setup | Done for the backend (`backend/.venv`) and the ZK prototype (`zk/`). Foundry is not installed |
| 2 | Database initialisation | Done: tables are created at startup; no migration tool |
| 3 | FastAPI scaffold | Foundation done: health, tasks, executions (with lifecycle), read endpoints for versions, evaluations and Critic feedback |
| 4 | Agent integration (Featherless) | **Not implemented.** Only research harnesses in `eval/` call the API |
| 5 | ZK circuit | Implemented as a standalone prototype with a development-only trusted setup. **Not integrated** into the backend |
| 6 | Smart contract deployment | Not implemented |
| 7 | Dashboard | Not implemented |
| 8 | Integration testing | Not implemented (backend and ZK have their own test suites) |

---

**End of Specification**

*This document defines the technical architecture and implementation boundaries for AutoEvolve Protocol. All implementation must adhere to these specifications.*