# AutoEvolve Protocol — Implementation Plan

**Version:** 1.0  
**Date:** October 30, 2026

---

## 1. Overview

This document outlines the 24-hour development sequence for AutoEvolve Protocol. The plan prioritizes core functionality that demonstrates the full workflow while maintaining feasibility within the hackathon timeframe.

---

## Implementation Status

This plan is the original schedule. Current state:

- **Implemented:** the ZK circuit prototype (`zk/`); the FastAPI + SQLite backend foundation (`backend/`).
- **Research only:** the Featherless comparison and Critic validation harnesses (`eval/`).
- **Not yet implemented:** Generator/Critic agents and orchestration, the revision acceptance engine, the evaluation execution engine, backend ZK/IPFS/blockchain integration, Solidity contracts, the Streamlit dashboard, cross-agent memory retrieval.

---

## 2. Development Timeline

### Phase 1: Foundation (Hours 1-6)

**Goal**: Set up project structure, database, and basic API

| Hour | Task | Deliverable |
|------|------|-------------|
| 1 | Environment setup | Python venv, dependencies installed |
| 1-2 | Project structure | All directories created, config files |
| 2-3 | Database schema | SQLite database with schema |
| 3-4 | FastAPI skeleton | API endpoints defined, basic routing |
| 4-5 | Service scaffolding | All service classes defined (no logic yet) |
| 5-6 | Dashboard skeleton | Streamlit app with navigation |

### Phase 2: Core Agent Logic (Hours 7-12)

**Goal**: Working Generator-Critic-Evaluator cycle

| Hour | Task | Deliverable |
|------|------|-------------|
| 7-8 | Generator service | Featherless API integration, code generation |
| 8-9 | Evaluator engine | Deterministic scoring, test execution |
| 9-10 | Critic service | AI feedback generation |
| 10-11 | Orchestrator | Workflow coordination, version tracking |
| 11-12 | Integration test | Full V1→V2 workflow working |

### Phase 3: ZK & Storage (Hours 13-18)

**Goal**: Proof generation, IPFS, Blockchain

| Hour | Task | Deliverable |
|------|------|-------------|
| 13-14 | Circom circuit | Improvement.circom defined and compiled |
| 14-15 | snarkjs integration | Proof generation and verification |
| 15-16 | IPFS service | Pinata integration, CID publication |
| 16-17 | Blockchain service | Smart contract, Sepolia registration |
| 17-18 | End-to-end test | Full workflow including ZK/IPFS/Blockchain |

### Phase 4: Cross-Agent & Dashboard (Hours 19-22)

**Goal**: Knowledge transfer and UI polish

| Hour | Task | Deliverable |
|------|------|-------------|
| 19-20 | Memory service | Cross-agent knowledge storage and retrieval |
| 20-21 | Agent 2 workflow | Knowledge inheritance demonstration |
| 21-22 | Dashboard pages | All 7 pages with real data |

### Phase 5: Polish & Testing (Hours 23-24)

**Goal**: Bug fixes, error handling, demo preparation

| Hour | Task | Deliverable |
|------|------|-------------|
| 23 | Error handling | Robust exceptions, user feedback |
| 24 | Demo testing | Full workflow dry run |

---

## 3. Milestones

### M1: Project Initialization (Hour 2)
- [ ] Virtual environment created and activated
- [ ] All dependencies installed
- [ ] Directory structure created
- [ ] `.env` file configured

### M2: Database Ready (Hour 4)
- [ ] SQLite schema deployed
- [ ] All tables created
- [ ] Migrations ready (not implemented: tables are created with `create_all`; no migration tool is in use)

### M3: API Functional (Hour 6)
- [ ] FastAPI server starts
- [ ] All endpoints respond
- [ ] Basic validation works

### M4: Agent Cycle Working (Hour 12)
- [ ] V1 generation successful
- [ ] Evaluation returns scores
- [ ] Critic provides feedback
- [ ] V2 generated with improvement

### M5: ZK Proof Operational (Hour 15)
- [ ] Circuit compiles
- [ ] Trusted setup complete
- [ ] Proof generates successfully
- [ ] Verification passes

### M6: Decentralized Storage (Hour 17)
- [ ] IPFS upload works
- [ ] CID retrieved successfully
- [ ] Blockchain registration succeeds
- [ ] Transaction confirmed on Sepolia

### M7: Knowledge Transfer (Hour 21)
- [ ] Memory stored from Agent 1
- [ ] Memory retrieved for Agent 2
- [ ] Agent 2 uses inherited knowledge
- [ ] Performance comparison visible

### M8: Dashboard Complete (Hour 22)
- [ ] All 7 pages implemented
- [ ] Real data displays correctly
- [ ] Charts render properly

### M9: Production Ready (Hour 24)
- [ ] No critical errors
- [ ] Demo scenario works end-to-end
- [ ] Error handling in place

---

## 4. Dependencies

### 4.1 Python Packages

| Package | Pinned version | Status | Purpose |
|---------|----------------|--------|---------|
| fastapi | 0.162.0 | Installed (`backend/requirements.txt`) | REST API framework (brings pydantic 2.x) |
| uvicorn | 0.54.0 | Installed | ASGI server |
| SQLAlchemy | 2.1.6 | Installed | ORM; used synchronously |
| pydantic-settings | 2.16.2 | Installed | Configuration (also installs python-dotenv) |
| pytest | 9.2.0 | Installed | Testing |
| httpx2 | 2.16.0 | Installed | Required by Starlette's TestClient |
| pandas, plotly, streamlit | not pinned | Planned | Dashboard milestone |
| web3 | not pinned | Planned | Ethereum interaction |

Not used: `aiosqlite` (the backend uses synchronous SQLAlchemy), `pytest-asyncio` (the tests are synchronous), and a separate `httpx` (replaced by `httpx2` for the test client).

### 4.2 Node.js Packages

| Package | Version | Status | Purpose |
|---------|---------|--------|---------|
| snarkjs | 0.7.6 | Installed locally in `zk/` | ZK proof operations |
| circomlib | 2.0.5 | Installed locally in `zk/` | Circom comparator and bit-decomposition templates |

The Circom compiler (2.2.3) is a separate binary downloaded to `zk/bin/circom.exe`; it is not an npm package.

### 4.3 External Services

| Service | Purpose | Account Required |
|---------|---------|------------------|
| Featherless API | AI generation/critique | API key |
| Pinata | IPFS storage | API key + secret |
| Ethereum Sepolia | On-chain registry | RPC URL + private key |

### 4.4 Development Tools

| Tool | Purpose |
|------|---------|
| Foundry | Smart contract development |
| Circom | ZK circuit compilation |
| Git | Version control |

---

## 5. Risk Management

### 5.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Featherless API unavailable | Medium | High | Mock service with fallback data |
| Circom compilation fails | Medium | High | Use pre-compiled circuit |
| Pinata rate limiting | Low | Medium | Implement retry with backoff |
| Sepolia congestion | Medium | Medium | Use fallback RPC, queue transactions |
| ZK proving too slow | Low | Medium | Pre-generate proof for demo |

### 5.2 Schedule Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Dependencies fail to install | Low | High | Use specific versions |
| Environment issues | Medium | High | Docker container option |
| Discovery of blocker | Medium | Medium | Buffer time in Phase 5 |

### 5.3 Demonstration Risks

| Risk | Mitigation |
|------|------------|
| Live API calls fail on demo day | Pre-record success scenarios |
| Network issues | Local fallback mode |
| ZK verification fails | Validate on smaller inputs first |

---

## 6. Fallback Decisions

### 6.1 AI API Fallback

If Featherless API is unavailable:
1. Use local LLM (Ollama) if available
2. Fall back to predefined solution templates
3. Display clear "API unavailable" status

### 6.2 Blockchain Fallback

If Sepolia is congested or RPC fails:
1. Use testnet faucet for gas
2. Queue transactions for later confirmation
3. Display "pending" status in dashboard

### 6.3 IPFS Fallback

If Pinata fails:
1. Use local IPFS node if available
2. Store data in SQLite as fallback
3. Simulate CID generation for demo

### 6.4 ZK Fallback

If Circom/snarkjs pipeline fails:
1. Pre-generate valid proof
2. Display proof artifacts from memory
3. Show "verification pending" status

---

## 7. Demo Scenario

### 7.1 Task

**"Implement an efficient sorting algorithm"**

### 7.2 Expected Outcome

| Version | Code | Score | Notes |
|---------|------|-------|-------|
| V1 | Bubble sort | 65 | Correct but O(n²) |
| V2 | Quicksort | 87 | Correct and O(n log n) |
| V3 | (if needed) | - | Based on improvement |

### 7.3 Metrics Displayed

- Correctness: 100% (both pass tests)
- Efficiency: V1=40, V2=85
- Code quality: V1=60, V2=80
- **Improvement**: 22 points

### 7.4 ZK Claim

```
Public signals: [65, 87, 22]
Proof: Verifies score_v2 > score_v1 + 20
```

### 7.5 IPFS Content

```json
{
  "task": "Implement an efficient sorting algorithm",
  "versions": [
    {"version": "v1", "code": "...", "score": 65},
    {"version": "v2", "code": "...", "score": 87}
  ],
  "improvement": 22,
  "zk_proof": "...",
  "timestamp": "..."
}
```

### 7.6 Blockchain Entry

- Execution ID: `0xabc123...`
- IPFS CID: `QmXyZ...`
- Score V1: 65
- Score V2: 87
- Delta: 22

---

## 8. Parallel Workstreams

### Stream 1: Backend (Lead Developer)
- FastAPI setup
- Services implementation
- Database operations

### Stream 2: ZK & Blockchain (Specialist)
- Circom circuit
- snarkjs integration
- Smart contract

### Stream 3: Dashboard (Frontend)
- Streamlit pages
- API integration
- Visualizations

### 8.1 Coordination Points

| Time | Sync Required |
|------|---------------|
| Hour 4 | API structure finalized |
| Hour 12 | Agent workflow integrated |
| Hour 18 | All services connected |
| Hour 22 | Full integration test |

---

## 9. Success Criteria

The project is successful if:

1. **Agent Workflow**: V1→V2→evaluation cycle completes automatically
2. **ZK Proof**: Valid proof generated and verified
3. **Storage**: IPFS CID obtained and blockchain transaction confirmed
4. **Knowledge Transfer**: Agent 2 retrieves and uses Agent 1's memory
5. **Dashboard**: All 7 pages display real backend data
6. **End-to-End**: Single command starts full demonstration

---

## 10. Command Reference

Run from the repository root in PowerShell. Only the commands marked *implemented* work today.

### Start Backend (implemented)
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### Run Backend Tests (implemented)
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

### Check Status (implemented)
```powershell
Invoke-RestMethod http://localhost:8000/api/health
```
The database is the SQLite file `backend/data/autoevolve.db`; open it with any SQLite client.

### Build and Test the ZK Prototype (implemented)
```powershell
cd zk
node scripts/build.js
node tests/run_tests.js
```

### Planned (no command exists yet)
Starting the Streamlit dashboard, running the demonstration, and querying the Sepolia registry with Foundry's `cast`.

---

**End of Implementation Plan**