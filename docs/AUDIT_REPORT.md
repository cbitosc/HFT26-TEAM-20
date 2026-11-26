# AutoEvolve Protocol — Architecture Audit Report

**Version:** 1.0  
**Date:** October 30, 2026

---

## 1. Critical Problems Discovered

### 1.1 ZK Proof Circuit (HIGH PRIORITY)

**Problem:** Original circuit included private hash inputs with NO constraints. This means:
- The hashes could be ANY value
- No actual binding to code versions
- Security theater, not security

**Fix Applied:** Removed non-functional hash inputs. Simplified to pure mathematical comparison.

### 1.2 Smart Contract Security

| Issue | Original | Fixed |
|-------|----------|-------|
| Duplicate execution IDs | No check | Added `exists` flag |
| Score validation | None | Added range checks |
| Task description on-chain | Stored | Removed (reduces data) |
| ZK proof on-chain | Not implemented | Documented trust model |

### 1.3 Evaluation Engine

**Problem:** "Execution Time" and "Token Efficiency" marked as deterministic, but they vary by environment.

**Fix Applied:** Split into:
- **Deterministic:** Test pass rate, correctness, code quality
- **Operational:** Execution time, token usage, cost

---

## 2. Changes Made to Specifications

| Document | Changes |
|----------|---------|
| `SPEC.md` | Updated ZK section, fixed evaluation engine, revised smart contract |
| `docs/ZK_TRUST_MODEL.md` | Complete rewrite with simplified circuit |
| `docs/CROSS_AGENT_EXPERIMENT.md` | NEW - Real experiment design |
| `docs/AUDIT_REPORT.md` | NEW - This report |

---

## 3. Final ZK Proof Design

### 3.1 Circuit (Simplified Secure)

```circom
pragma circom 2.0.0;
include "comparators.circom";

template ImprovementProof() {
    signal input score_v1;   // Public: 0-100
    signal input score_v2;   // Public: 0-100
    signal input delta;      // Public: minimum improvement
    
    signal improvement;
    improvement <== score_v2 - score_v1;
    
    component gt = GreaterThan(256);
    gt.in[0] <== improvement;
    gt.in[1] <== delta;
    gt.out === 1;
}

component main {public [score_v1, score_v2, delta]} = ImprovementProof();
```

### 3.2 What It Proves

✅ `score_v2 > score_v1 + δ` (mathematical fact)

### 3.3 What It Does NOT Prove

❌ Evaluator honesty (assumed trust)  
❌ AI intelligence  
❌ Code correctness  
❌ Semantic quality

---

## 4. Final Smart Contract Trust Model

### 4.1 Contract Features

```solidity
// Key security features:
// - Duplicate prevention (require(!exists))
// - Score validation (require(scoreV1 <= 100))
// - No task description (reduces on-chain data)
// - No access control (appropriate for testnet)
```

### 4.2 Trust Model

| Component | Status |
|-----------|--------|
| ZK Proof on-chain | ❌ NOT implemented |
| Proof verification | ✅ Off-chain via snarkjs |
| Score accuracy | ❌ Assumed from backend |
| IPFS CID | ✅ Stored immutably |
| Timestamp | ✅ Block timestamp |

**Conclusion:** Contract is a MINIMAL registry. It provides immutability but does NOT verify ZK proofs. Trust assumption: Backend provides accurate scores.

---

## 5. Final Deterministic Evaluation Design

### 5.1 Deterministic (Reproducible)

| Metric | Range | Weight |
|--------|-------|--------|
| Test Pass Rate | 0-100 | 50% |
| Correctness | 0-100 | 30% |
| Code Quality | 0-100 | 20% |

### 5.2 Operational (Varies)

| Metric | Notes |
|--------|-------|
| Execution Time | System-dependent |
| Token Usage | API-dependent |
| Cost | Pricing-dependent |

### 5.3 Formula

```
total_score = (test_pass_rate * 0.5) + (correctness * 0.3) + (code_quality * 0.2)
```

Same evaluation applies to V1, V2, V3.

---

## 6. Cross-Agent Experiment Design

### 6.1 Three-Scenario Comparison

1. **Agent 1:** Original execution → stores memory
2. **Agent 2 (No Memory):** Baseline performance
3. **Agent 2 (With Memory):** Tests knowledge transfer

### 6.2 Task Class

Use related but different tasks:
- Agent 1: "Implement efficient sorting"
- Agent 2: "Sort strings alphabetically"

### 6.3 Metrics

| Metric | Without Memory | With Memory | Expected |
|--------|---------------|-------------|----------|
| V1 Score | 70 | 85 | +15 |
| Iterations | 2 | 1 | -1 |

### 6.4 Memory Lineage

Each execution with inherited knowledge records:
- Source execution ID
- Memory ID used
- Patterns applied
- Performance contribution

---

## 7. Revised API Lifecycle

### 7.1 Execution States

```
queued → generating_v1 → evaluating_v1 → critiquing → 
generating_v2 → evaluating_v2 → [generating_v3] → 
zk_proof → ipfs_publish → blockchain_register → completed
```

### 7.2 Key IDs

| ID Type | Format | Purpose |
|---------|--------|---------|
| task_id | UUID v4 | User-submitted task |
| execution_id | UUID v4 | Single workflow run |
| version_id | UUID v4 | V1, V2, V3 code |
| proof_id | UUID v4 | ZK proof artifact |
| memory_id | UUID v4 | Cross-agent knowledge |
| execution_id (blockchain) | bytes32 | On-chain identifier |

### 7.3 Error Handling

| Code | Status | Scenario |
|------|--------|----------|
| VALIDATION_ERROR | 400 | Invalid input |
| NOT_FOUND | 404 | Resource missing |
| AI_API_ERROR | 503 | Featherless unavailable |
| IPFS_ERROR | 503 | Pinata unavailable |
| BLOCKCHAIN_ERROR | 503 | Sepolia unavailable |
| ZK_ERROR | 500 | Proof generation fails |

---

## 8. Remaining Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Circom on Windows | HIGH | Use WSL2 or Docker |
| Featherless API | HIGH | Fallback templates |
| Sepolia congestion | MEDIUM | Queue transactions |
| 24-hour time constraint | HIGH | P0/P1/P2 prioritization |
| Node.js 24.x compatibility | MEDIUM | May need downgrade to v20 |

---

## 9. Features Simplified or Postponed

### 9.1 Removed/Simplified

| Feature | Reason |
|---------|--------|
| Code hash binding in ZK | Non-functional, removed |
| On-chain ZK verification | Too complex, off-chain only |
| Task description on-chain | Reduces data, privacy |
| Semantic memory matching | Keyword matching only |

### 9.2 Postponed to P2

- Advanced memory retrieval (semantic search)
- Comprehensive test coverage metrics
- Multiple evaluation criteria
- Advanced visualizations

---

## 10. Confirmation

**Checklist:**

- ✅ No application code created
- ✅ No packages installed
- ✅ No circuits implemented
- ✅ No contracts implemented
- ✅ No external services configured
- ✅ Only documentation updated/created

**Files Created/Modified:**
- `SPEC.md` - Updated
- `docs/ZK_TRUST_MODEL.md` - Rewritten
- `docs/CROSS_AGENT_EXPERIMENT.md` - New
- `docs/AUDIT_REPORT.md` - New

---

**End of Audit Report**

*This audit refined the specifications to be honest about what can be verified within the 24-hour scope. The ZK proof now proves only mathematical score comparison, and the smart contract is documented as a minimal registry without on-chain proof verification.*