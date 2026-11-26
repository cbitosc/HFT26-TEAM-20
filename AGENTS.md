# AutoEvolve Protocol — Agent Development Guidelines

**Version:** 1.0  
**Date:** October 30, 2026

---

## 1. Project-Wide Coding Instructions

### 1.1 Core Principles

- **Truthfulness**: Never fake data or mock functionality that should be real
- **Traceability**: Every displayed metric must come from actual backend results
- **Transparency**: Clearly label any sample/preview data
- **Integrity**: ZK proofs must prove what they claim, no more no less

### 1.2 Architecture Boundaries

| Layer | Allowed Access |
|-------|---------------|
| **Dashboard (React web app, per the PRD; replaces the earlier Streamlit plan)** | FastAPI HTTP calls only |
| **FastAPI Backend** | SQLite, AI API, IPFS, Blockchain |
| **Services** | Their specific external integrations only |

**NEVER** bypass these boundaries. Example violations:
- ❌ Dashboard directly calling Pinata API
- ❌ Backend displaying hardcoded "sample" scores as real data
- ❌ ZK service claiming to prove "AI intelligence"

---

## 2. Security Requirements

### 2.1 Secrets Management

| Secret Type | Storage | Access Pattern |
|-------------|---------|----------------|
| API Keys | Environment variables (.env) | Read at runtime |
| Private Keys | Environment variables | Never log, never display |
| Database URLs | Environment variables | Connection pooling |
| Contract Addresses | Environment variables | Configuration |

### 2.2 Prohibited Actions

- ❌ Committing secrets to version control
- ❌ Hardcoding credentials in source files
- ❌ Logging private keys or API secrets
- ❌ Displaying sensitive values in dashboard
- ❌ Storing credentials in database

### 2.3 Environment File Template

Create `.env.example` with placeholder values:

```env
# API Configuration
FEATHERLESS_API_KEY=YOUR_API_KEY_HERE

# IPFS/Pinata
PINATA_API_KEY=YOUR_PINATA_KEY
PINATA_API_SECRET=YOUR_PINATA_SECRET

# Ethereum Sepolia
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
PRIVATE_KEY=YOUR_PRIVATE_KEY_HERE
CONTRACT_ADDRESS=DEPLOYED_CONTRACT_ADDRESS

# Database
DATABASE_URL=sqlite:///./autoevolve.db
```

Add to `.gitignore`:
```
.env
*.env
.env.local
```

---

## 3. API Key and Secret Handling

### 3.1 Featherless API

```python
# CORRECT: Load from environment
import os
api_key = os.environ.get("FEATHERLESS_API_KEY")

# NEVER do this:
# api_key = "sk-actual-key-here"  # ❌
```

### 3.2 Ethereum Private Key

```python
# CORRECT: Load from environment, validate presence
private_key = os.environ.get("PRIVATE_KEY")
if not private_key:
    raise ValueError("PRIVATE_KEY environment variable not set")

# NEVER do this:
# private_key = "0xabc123..."  # ❌
```

### 3.3 Pinata API

```python
# CORRECT: Use environment variables for authentication
headers = {
    "pinata_api_key": os.environ.get("PINATA_API_KEY"),
    "pinata_api_secret": os.environ.get("PINATA_API_SECRET")
}
```

---

## 4. Testing Requirements

### 4.1 Unit Tests

- Every service class must have unit tests
- Mock external dependencies (API calls, blockchain calls)
- Test error handling paths

### 4.2 Integration Tests

- Test API endpoints with real database
- Test service-to-service communication
- Verify data flow end-to-end

### 4.3 ZK Proof Tests

| Test Type | Purpose |
|-----------|---------|
| **Valid Proof** | Generate proof with known scores (v1=65, v2=82), verify passes |
| **Invalid Proof** | Generate proof claiming v2 ≤ v1, verify fails |
| **Boundary Test** | Test exactly at threshold (v2 = v1 + δ) |

### 4.4 Smart Contract Tests

- Deployment test
- Registration test
- Retrieval test
- Event emission test

---

## 5. Rules Against Fake Data and Misleading ZK Claims

### 5.1 Fake Data Prohibition

| Component | Real Data Required |
|-----------|-------------------|
| Task submissions | Actual user input |
| Generated solutions | Real AI API responses |
| Evaluation scores | Deterministic calculation results |
| Critic feedback | Real AI API responses |
| IPFS CIDs | Actual Pinata upload response |
| Blockchain transactions | Actual Sepolia transaction hashes |

**Sample Data Rule**: If displaying sample data for UI development, explicitly label with `SAMPLE DATA` or `PREVIEW` badge.

### 5.2 ZK Claim Accuracy

**What the ZK Proof PROVES:**
- Mathematical comparison: `score_v2 > score_v1 + δ`
- Bound to specific committed values
- Verification reveals nothing about code contents

**What the ZK Proof DOES NOT PROVE:**
- ❌ AI intelligence or reasoning quality
- ❌ Correctness of the solution
- ❌ Semantic quality of code
- ❌ Truth of critic's analysis
- ❌ Validity of evaluation methodology

**Correct Claim Format:**
```
"Zero-knowledge proof verifies that version V2 achieved a 
deterministic score strictly greater than V1 by at least δ points, 
without revealing the underlying code or evaluation details."
```

**Prohibited Claim Format:**
```
"Zero-knowledge proof proves the AI improved its solution"  # ❌ Too vague
"ZK proves the solution is correct"  # ❌ Overclaiming
```

---

## 6. Database Consistency

### 6.1 Data Model

| Entity | Description |
|--------|-------------|
| Task | User-submitted coding challenge |
| Execution | Single run of the evolution workflow |
| Version | Generated solution (V1, V2, V3) |
| Evaluation | Deterministic score for a version |
| Critique | AI-generated feedback |
| ZKProof | Proof artifact and verification status |
| Memory | Cross-agent knowledge store |

### 6.2 Relationships

```
Task (1) ──── (M) Execution
Execution (1) ──── (M) Version
Version (1) ──── (M) Evaluation
Version (1) ──── (1) Critique
Execution (1) ──── (1) ZKProof
Execution (1) ──── (M) Memory (for knowledge transfer)
```

---

## 7. Error Handling

### 7.1 API Error Responses

```python
from fastapi import HTTPException

# Use appropriate status codes
raise HTTPException(status_code=400, detail="Invalid task description")
raise HTTPException(status_code=404, detail="Execution not found")
raise HTTPException(status_code=500, detail="AI API call failed")
```

### 7.2 Service Error Handling

- Log errors with context
- Return meaningful error messages
- Allow graceful degradation where possible

---

## 8. Performance Considerations

### 8.1 Async Usage

Use async operations for:
- External API calls (Featherless, Pinata, Ethereum RPC)
- Database queries
- File I/O

Use synchronous operations for:
- CPU-bound evaluation logic
- ZK proof generation (typically blocking)

### 8.2 Timeouts

| Service | Timeout |
|---------|---------|
| Featherless API | 60 seconds |
| Pinata API | 30 seconds |
| Ethereum RPC | 120 seconds |
| Database | 10 seconds |

---

## 9. Compliance Checklist

Before committing code, verify:

- [ ] No hardcoded secrets or API keys
- [ ] All environment variables documented in `.env.example`
- [ ] Sample data clearly labeled
- [ ] ZK claims accurately describe what's proven
- [ ] Dashboard shows only real backend data
- [ ] Error handling in place for all external calls
- [ ] Tests cover critical paths

---

**End of Agent Guidelines**