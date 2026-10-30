# 🚀 CBIT Hacktoberfest '26 — Project Starter Repository

> **Official Public Starter Repository for CBIT Hacktoberfest '26**  
> *Chaitanya Bharathi Institute of Technology (CBIT), Hyderabad*

---

## 📋 Team Information

| Attribute | Details |
| :--- | :--- |
| **Team Name** | **The vigilantes** |
| **Team Number** | `TEAM-20` (`HFT26-TEAM-20`) |
| **Registration ID** | `HFEST26-8CHLSV52` |
| **Problem Track** | **Track Selection in Progress** |
| **Domain** | `General Track` |
| **Team Leader** | Parth Joshi (parth.joshi_25ucs@sanjivani.edu.in) |
| **Institution** | Sanjivani University, Kopargaon Maharashtra |

### 👥 Team Members

| # | Name | Email | Institution |
| :--- | :--- | :--- | :--- |
| 1 | Kunal Kulkarni | kunal.kulkarni_25ucs@sanjivani.edu.in | Sanjivani University, Kopargaon Maharashtra |
| 2 | Snehal Ranade | snehal.ranade24@sanjivani.edu.in | Sanjivani University, Kopargaon Maharashtra |
| 3 | Prachi Bhujbal | prachi.bhujbal24@sanjivani.edu.in | Sanjivani University, Kopargaon Maharashtra |

---

## 🎯 Problem Statement

### **Track Selection in Progress**
*Domain:* **General Track**

Details regarding the chosen problem statement track and technical requirements.

---

## 🛠️ Contribution & Submission Workflow

All teams must follow the official fork-and-pull-request workflow:

1. **Fork this Repository**:
   - One team member should click the **Fork** button at the top right to fork this upstream repository to your personal/team GitHub account.
2. **Add Collaborators**:
   - In your forked repository, navigate to **Settings > Collaborators** and invite all your registered team members.
3. **Clone & Develop Locally**:
   ```bash
   git clone https://github.com/<your-username>/HFT26-TEAM-20.git
   cd HFT26-TEAM-20
   git checkout -b feature/prototype
   ```
4. **Commit & Push Regularly**:
   - Make atomic, descriptive commits throughout the hackathon.
   ```bash
   git add .
   git commit -m "feat: implement core solution architecture"
   git push origin feature/prototype
   ```
5. **Open Pull Request (PR) for Final Submission**:
   - When ready for evaluation, open a **Pull Request** from your fork's `main` branch back to this upstream repository's `main` branch.
   - **PR Title Format**: `[SUBMISSION] TEAM-20 - The vigilantes - Track Selection in Progress`
   - **PR Description Checklist**:
     - 📌 Solution Overview & Approach
     - 🏗️ Architecture & Tech Stack Details
     - 🚀 Local Setup & Installation Instructions
     - 🎥 Demo Video Link / Live Deployment URL
     - 📸 Key Screenshots & Visuals

---

## 📁 Recommended Project Structure

```
.
├── src/                  # Source code (Frontend / Backend / ML)
├── docs/                 # Documentation, architecture diagrams, slides
├── tests/                # Test suites & verification scripts
├── README.md             # Your project documentation & presentation
└── LICENSE               # Open-source license (MIT recommended)
```

---

## ⚠️ Important Rules & Code of Conduct
* **Upstream Protection**: Do not push directly to this repository's main branch. All evaluation will be conducted on your submitted Pull Request.
* **Original Work**: All code submitted must be developed during the hackathon timeline. Open-source libraries and frameworks are welcomed with proper attribution.
* **Code Freeze**: Final Pull Requests must be submitted before the designated hackathon submission deadline.

---

<!-- ===== AutoEvolve Protocol project documentation (added below the team starter template) ===== -->

# AutoEvolve Protocol

**Autonomous Agent Framework with Verifiable Improvement Claims**

---

## 1. Project Overview

AutoEvolve Protocol demonstrates an autonomous AI agent framework that iteratively improves its solutions through structured critique, with every improvement claim verifiable through zero-knowledge proofs and immutable on-chain registration.

### 1.1 Problem Statement

AI-generated solutions lack:
- **Verifiability**: No cryptographic proof that improvements actually occurred
- **Transparency**: No immutable record of the evolution process
- **Knowledge Transfer**: No mechanism for one agent to learn from another's execution

### 1.2 Solution

AutoEvolve Protocol creates a verifiable improvement loop:
1. Generator produces initial solution (V1)
2. Evaluator measures performance with deterministic metrics
3. Critic identifies weaknesses
4. Generator produces improved version (V2)
5. ZK proof cryptographically verifies the improvement
6. Execution history published to IPFS
7. CID registered on Ethereum Sepolia
8. Second agent inherits knowledge for new tasks

### 1.3 Current Implementation Status

Sections 4, 5 and 9 below describe the *intended* demonstration. This table says what exists today.

| Component | Status |
|-----------|--------|
| FastAPI + SQLite backend foundation (tasks, executions, validated lifecycle, versions, evaluations, Critic feedback storage, health check) | **Implemented** (`backend/`) |
| ZK improvement proof (Circom circuit, Groth16 proof and verification, 10 test cases, tampering test) | **Implemented as a standalone prototype** (`zk/`); development-only trusted setup; not called by the backend |
| Featherless model comparison and Critic validation harnesses | **Research tooling** (`eval/`); not part of the application |
| Generator and Critic agents, orchestration, revision acceptance engine | Not yet implemented |
| Evaluation execution engine (running candidate code against tests) | Not yet implemented |
| Backend integration of ZK proofs, IPFS (Pinata), Sepolia registry | Not yet implemented |
| Solidity contracts and Foundry deployment | Not yet implemented |
| Streamlit dashboard | Not yet implemented |
| Cross-agent memory retrieval | Not yet implemented (only a minimal storage table exists) |

---

## 2. Technology Stack

| Layer | Technology |
|-------|------------|
| Dashboard | Streamlit |
| Data Processing | Pandas |
| Visualizations | Plotly |
| Backend | Python + FastAPI |
| AI API | Featherless API |
| Agent Orchestration | Python |
| Evaluation | Deterministic Python |
| Database | SQLite |
| ZK Circuits | Circom |
| ZK Proof System | snarkjs |
| Smart Contracts | Solidity |
| Contract Tooling | Foundry |
| Blockchain | Ethereum Sepolia |
| Decentralized Storage | IPFS via Pinata |
| Version Control | Git / GitHub |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DASHBOARD LAYER                          │
│                     (Streamlit)                             │
│  - Command Center   - Evolution Lab   - Analytics          │
│  - ZK Center        - IPFS View       - Blockchain         │
│  - Agent Comparison                                        │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/REST
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      REST API LAYER                         │
│                       (FastAPI)                             │
│  /tasks /executions /versions /zk-proofs /ipfs /blockchain │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐
│   Agent     │    │   ZK        │    │    Storage          │
│  Services   │    │   Service   │    │    Services         │
│             │    │             │    │                     │
│ - Generator │    │ - Circom    │    │ - IPFS/Pinata       │
│ - Critic    │    │ - snarkjs   │    │ - SQLite            │
│ - Evaluator │    │             │    │ - Blockchain        │
└─────────────┘    └─────────────┘    └─────────────────────┘
```

---

## 4. Main Demonstration Scenario

### Scenario: Sorting Algorithm Improvement

1. **Task Submission**: Developer submits "Implement efficient sorting"
2. **V1 Generation**: AI produces bubble sort (score: 65)
3. **Evaluation**: Correctness ✓, Efficiency ✗ (O(n²))
4. **Critique**: "Consider quicksort or mergesort for better time complexity"
5. **V2 Generation**: AI produces quicksort (score: 87)
6. **Evaluation**: Correctness ✓, Efficiency ✓ (O(n log n))
7. **ZK Proof**: Proves score_v2 > score_v1 by 22+ points
8. **IPFS**: Publication returns CID `QmXyZ...`
9. **Blockchain**: Transaction registers CID on Sepolia
10. **Agent 2**: Retrieves memory, applies sorting optimization knowledge to new task
11. **Dashboard**: Complete workflow visualized

---

## 5. Key Features

### 5.1 Verifiable Improvement Claims
- Zero-knowledge proofs verify numerical score improvement
- Cannot be faked - cryptographic verification required

### 5.2 Immutable Execution Record
- Full history stored on IPFS
- CID registered on Ethereum Sepolia
- Tamper-proof and publicly accessible

### 5.3 Cross-Agent Knowledge Transfer
- Agent 2 can retrieve Agent 1's execution context
- Demonstrates actual knowledge inheritance
- Performance comparison tracked

### 5.4 Complete Workflow Visualization
- Streamlit dashboard shows every step
- Version comparisons with code diffs
- Real-time status updates

---

## 6. Project Structure

Each directory is marked **implemented**, **research tooling**, or **planned** (not created yet).

```
CBIT/
├── README.md, SPEC.md, AGENTS.md
├── FEATHERLESS_CRITIC_VALIDATION_REPORT.md   # research result
│
├── backend/                 # IMPLEMENTED: FastAPI + SQLite foundation
│   ├── app/
│   │   ├── main.py, config.py, database.py, init_db.py
│   │   ├── lifecycle.py, scoring.py, errors.py
│   │   └── models/  schemas/  services/  api/
│   ├── tests/               # pytest suite
│   └── requirements.txt, pytest.ini, .env.example, README.md
│
├── zk/                      # IMPLEMENTED: standalone ZK prototype (not yet called by the backend)
│   ├── circuits/improvement_proof.circom
│   ├── scripts/build.js     # compile + development-only trusted setup
│   ├── tests/run_tests.js
│   └── package.json
│
├── eval/                    # RESEARCH TOOLING: Featherless comparison / Critic validation harnesses and results
├── docs/                    # documentation
│
├── dashboard/               # PLANNED: Streamlit dashboard (not created)
└── contracts/               # PLANNED: Solidity + Foundry (not created)
```

The SQLite database is created automatically by the backend (default `backend/data/autoevolve.db`, git-ignored). There is no SQL schema file and no migration tool; tables are created with SQLAlchemy `create_all` at startup.

---

## 7. Setup Instructions

### Prerequisites

- Python 3.12+
- Node.js 18+ (24.x was used)
- Windows PowerShell (the commands below are PowerShell)
- Git is optional; this directory is not currently a Git repository

### 7.1 Backend (implemented)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env                              # optional; defaults work without it
.\.venv\Scripts\python.exe -m app.init_db           # optional; startup also creates the tables
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest                # run the test suite
```

Interactive API documentation is served at `http://127.0.0.1:8000/docs`. See `backend/README.md` for configuration.

### 7.2 ZK prototype (implemented, standalone)

```powershell
cd zk
npm install                                         # snarkjs and circomlib, installed locally
# Download circom v2.2.3 (circom-windows-amd64.exe) from https://github.com/iden3/circom/releases
# and save it as zk\bin\circom.exe
node scripts/build.js                               # compile + DEVELOPMENT-ONLY trusted setup
node tests/run_tests.js                             # 10 cases + tampering test
```

The trusted setup is single-party and for development only. See `docs/ZK_TRUST_MODEL.md`.

### 7.3 Planned (no setup exists yet)

The Streamlit dashboard, the Solidity/Foundry contracts, IPFS (Pinata) and Sepolia integration are not implemented, so there are no installation or start commands for them. The research harnesses in `eval/` read `FEATHERLESS_API_KEY` from the environment if you want to rerun them.

---

## 8. API Endpoints

### 8.1 Implemented endpoints

All paths are under `/api`. Full request and response schemas are in `docs/API_CONTRACT.md`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Backend and database status |
| `/api/tasks` | POST, GET | Create a task; list tasks |
| `/api/tasks/{task_id}` | GET | Get a task |
| `/api/tasks/{task_id}/executions` | POST | Create a queued execution (nothing runs it yet) |
| `/api/executions` | GET | List executions |
| `/api/executions/{execution_id}` | GET | Execution details and status history |
| `/api/executions/{execution_id}/cancel` | POST | Cancel a non-terminal execution |
| `/api/executions/{execution_id}/versions` | GET | List versions of an execution |
| `/api/versions/{version_id}` | GET | Get a version |
| `/api/versions/{version_id}/evaluations` | GET | Evaluation history of a version |
| `/api/versions/{version_id}/critic-feedback` | GET | Stored Critic feedback of a version |

There is deliberately no endpoint for clients to submit evaluation scores, accept or reject a version, or claim an improvement.

### 8.2 Planned endpoints (not implemented)

ZK proof generation and verification, IPFS publication and retrieval, blockchain registration, cross-agent memory retrieval and storage, and any endpoint that runs the Generator, Critic or Evaluator.

---

## 9. Demonstration Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Submit  │───▶│ Generate │───▶│ Evaluate │───▶│ Critique │
│  Task    │    │    V1    │    │    V1    │    │    V1    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                      │
                                                      ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Dashboard│◀───│ Blockchain│◀───│   IPFS   │◀───│ Generate │
│   View   │    │ Register │    │ Publish  │    │    V2    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
       │                                            │
       │            ┌──────────┐                    │
       └───────────▶│  Agent 2 │◀───────────────────┘
                    │  Memory  │
                    │ Retrieve │
                    └──────────┘
```

---

## 10. License

MIT License

---

**AutoEvolve Protocol** — *Verifiable AI Improvement Through Zero-Knowledge Proofs*