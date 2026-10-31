# AutoEvolve Protocol — ZK Trust Model

**Version:** 6.0 (implemented and tested prototype)
**Date:** October 30, 2026

---

## 1. Status

| Stage | Status | Evidence |
|-------|--------|----------|
| Specification approved | ✅ Done | Prompt 02.4 freeze |
| Implemented | ✅ Done | `zk/circuits/improvement_proof.circom` |
| Compiled | ✅ Done | circom 2.2.3, exit 0, 82 constraints |
| Witness-tested | ✅ Done | 10/10 cases behaved as expected |
| Proof-generated | ✅ Done | Groth16 proofs for cases 1, 2, 5 |
| Proof-verified | ✅ Done | `snarkjs groth16 verify` returned `OK!` for cases 1, 2, 5 |
| Tampering rejected | ✅ Done | 2 altered public-input files rejected (`Invalid proof`, exit 1) |
| Production trusted setup | ❌ Not done | Development-only single-party setup |
| On-chain verifier | ❌ Not done | Out of scope for this milestone |

---

## 2. Exact Claim

The proof establishes only this statement about three **public** integers:

```
0 <= score_v1 <= 100
0 <= score_v2 <= 100
1 <= delta    <= 50
score_v2 >= score_v1 + delta        (equality passes)
```

It does **not** establish:

- that the scores correspond to particular source-code versions (no version binding)
- that the evaluator computed the scores honestly
- that the code is correct or of good quality
- that an LLM improved its reasoning, or that the improvement is meaningful

**Privacy:** all three inputs are public. The proof hides nothing; anyone can check the inequality by hand. Its value is a standard, verifiable artifact of the claim that a future on-chain or third-party verifier can check against a fixed verification key.

---

## 3. Toolchain (actually installed and used)

| Tool | Version | Source | Install location |
|------|---------|--------|------------------|
| circom | 2.2.3 | Official release `circom-windows-amd64.exe` from github.com/iden3/circom (12,039,168 bytes, matched release asset size) | `zk/bin/circom.exe` (gitignored) |
| snarkjs | 0.7.6 | npm | `zk/node_modules` (local, not global) |
| circomlib | 2.0.5 | npm | `zk/node_modules` (local, not global) |
| Node.js | 24.13.0 | pre-existing | system |

**Environment choice:** native Windows. WSL2 had only the `docker-desktop` system distribution (no general Linux distro). The Docker daemon was not running, and no official circom image exists, so Docker would have meant building a Rust toolchain image with 10.4 GB free disk. The official circom release ships a Windows binary, and snarkjs/circomlib are pure JavaScript, so native tooling is supported and was verified working end to end.

SHA-256 of the downloaded binary: `E43F132EE6F0AA79B705BECEB59C2A7E6A54D7BDEAB917CA34E9FC1951D185E1`. iden3 does not publish a checksum file for this release, so this hash is recorded for reproducibility, not checked against an upstream value.

---

## 4. Comparator Semantics (verified against installed circomlib 2.0.5 source)

From `node_modules/circomlib/circuits/comparators.circom`:

```circom
template LessThan(n) {
    assert(n <= 252);
    signal input in[2];
    signal output out;
    component n2b = Num2Bits(n+1);
    n2b.in <== in[0]+ (1<<n) - in[1];
    out <== 1-n2b.out[n];
}
template LessEqThan(n) {      // out = 1 iff in[0] <= in[1]
    ...
    lt.in[0] <== in[0];
    lt.in[1] <== in[1]+1;
}
template GreaterThan(n) {     // out = 1 iff in[0] > in[1]
    ...
    lt.in[0] <== in[1];
    lt.in[1] <== in[0];
}
```

**Correction to v5.0:** v5.0 stated that `LessEqThan` is built on `GreaterThan`. In the installed library it is built on `LessThan(in[0], in[1] + 1)`. The semantics (`in[0] <= in[1]`) are the same.

**Soundness precondition:** `LessThan(n)` is only correct when both of its inputs are below `2^n`. It does not range-check its inputs itself. The circuit therefore range-checks every value with `Num2Bits` before any comparison (section 6).

---

## 5. Implemented Circuit

File: `zk/circuits/improvement_proof.circom`

```circom
pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/bitify.circom";
include "../node_modules/circomlib/circuits/comparators.circom";

template ImprovementProof() {
    signal input score_v1;
    signal input score_v2;
    signal input delta;

    component v1Bits = Num2Bits(7);
    v1Bits.in <== score_v1;
    component v1Le100 = LessEqThan(7);
    v1Le100.in[0] <== score_v1;
    v1Le100.in[1] <== 100;
    v1Le100.out === 1;

    component v2Bits = Num2Bits(7);
    v2Bits.in <== score_v2;
    component v2Le100 = LessEqThan(7);
    v2Le100.in[0] <== score_v2;
    v2Le100.in[1] <== 100;
    v2Le100.out === 1;

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

    signal target;
    target <== score_v1 + delta;

    component mainClaim = LessEqThan(8);
    mainClaim.in[0] <== target;
    mainClaim.in[1] <== score_v2;
    mainClaim.out === 1;
}

component main {public [score_v1, score_v2, delta]} = ImprovementProof();
```

(The file in the repository also contains explanatory comments.)

---

## 6. Constraint Inventory

| # | Constraint | Enforces | Why the comparator is sound |
|---|-----------|----------|-----------------------------|
| 1 | `Num2Bits(7)` on score_v1 | 0 ≤ score_v1 < 128 | Rejects negatives and field wrap-around |
| 2 | `LessEqThan(7)(score_v1, 100) === 1` | score_v1 ≤ 100 | LessThan(7) inputs: score_v1 < 128, 101 < 128 |
| 3 | `Num2Bits(7)` on score_v2 | 0 ≤ score_v2 < 128 | |
| 4 | `LessEqThan(7)(score_v2, 100) === 1` | score_v2 ≤ 100 | inputs < 128 |
| 5 | `Num2Bits(6)` on delta | 0 ≤ delta < 64 | |
| 6 | `LessEqThan(6)(delta, 50) === 1` | delta ≤ 50 | inputs: delta < 64, 51 < 64 |
| 7 | `GreaterThan(6)(delta, 0) === 1` | delta ≥ 1 | inputs: 0, delta < 64 |
| 8 | `target <== score_v1 + delta` | target defined | No subtraction, so no underflow |
| 9 | `LessEqThan(8)(target, score_v2) === 1` | **score_v2 ≥ score_v1 + delta** | target ≤ 150 < 256 and score_v2 + 1 ≤ 101 < 256 |

**`target <= 150` omitted.** Constraints 2 and 6 already imply target ≤ 150, and constraints 1 and 5 alone imply target ≤ 190 < 256, which is all constraint 9 needs. The defensive check would add constraints without adding safety.

**Unconstrained signals:** none. The compiler reports `CA02` warnings that the `out[]` bits of the `Num2Bits` range checks are not used by the parent template. This is expected: each bit is constrained inside `Num2Bits` (`out[i] * (out[i] - 1) === 0` and `lc1 === in`); the range check is the purpose of the component, not the bits.

---

## 7. Compilation Result (executed)

Command (from `zk/`):

```
bin\circom.exe circuits\improvement_proof.circom --r1cs --wasm --sym --inspect -o build
```

| Metric | Value |
|--------|-------|
| Exit status | 0 ("Everything went okay") |
| Template instances | 12 |
| Non-linear constraints | 59 |
| Linear constraints | 23 |
| Total constraints (`snarkjs r1cs info`) | 82 |
| Public inputs | 3 |
| Private inputs | 0 |
| Wires | 73 |
| Curve | bn-128 |
| Warnings | CA02 only (explained in section 6) |

---

## 8. Trusted Setup — DEVELOPMENT ONLY

Executed by `zk/scripts/build.js`:

1. `powersoftau new bn128 8` (2^8 = 256 ≥ 82 constraints + public inputs)
2. `powersoftau contribute` (one contribution, random entropy generated in-process and never printed)
3. `powersoftau prepare phase2`
4. `powersoftau verify`
5. `groth16 setup` (circuit-specific)
6. `zkey contribute` (one contribution)
7. `zkey verify` → `ZKey Ok!`
8. `zkey export verificationkey` → `build/verification_key.json`

**Limitations:** both phases were run by a single party on one machine. Anyone who ran this setup could in principle have retained the toxic waste and could forge proofs for false statements. This setup gives no production trust guarantee. Production use needs a public multi-party Powers of Tau file and an independent multi-party phase-2 ceremony.

Every rebuild produces a new proving key and verification key. Proofs from one build do not verify against keys from another build.

---

## 9. Proof Procedure

From `zk/`, using `S = node node_modules\snarkjs\build\cli.cjs`:

```
S wtns calculate build\improvement_proof_js\improvement_proof.wasm input.json witness.wtns
S wtns check build\improvement_proof.r1cs witness.wtns
S groth16 prove build\improvement_proof_final.zkey witness.wtns proof.json public.json
S groth16 verify build\verification_key.json public.json proof.json
```

`input.json` format: `{"score_v1": "65", "score_v2": "75", "delta": "10"}`.
`public.json` order follows the main declaration: `[score_v1, score_v2, delta]`.

---

## 10. Test Results (executed with `node tests/run_tests.js`)

| # | v1 | v2 | δ | Expected | Actual | Where it stopped |
|---|---:|---:|---:|---|---|---|
| 1 | 65 | 82 | 10 | PASS | PASS | Proof verified |
| 2 | 65 | 75 | 10 | PASS | PASS | Proof verified (equality case) |
| 3 | 65 | 74 | 10 | FAIL | FAIL | Witness rejected: `mainClaim.out === 1` |
| 4 | 82 | 65 | 10 | FAIL | FAIL | Witness rejected: `mainClaim.out === 1` |
| 5 | 0 | 100 | 50 | PASS | PASS | Proof verified |
| 6 | 100 | 100 | 1 | FAIL | FAIL | Witness rejected: `mainClaim.out === 1` |
| 7 | 65 | 150 | 10 | FAIL | FAIL | Witness rejected: `Num2Bits(7)` (`lc1 === in`), since 150 ≥ 128 |
| 8 | 65 | 80 | 0 | FAIL | FAIL | Witness rejected: `deltaGt0.out === 1` |
| 9 | 65 | 80 | 51 | FAIL | FAIL | Witness rejected: `deltaLe50.out === 1` |
| 10 | −5 | 50 | 10 | FAIL | FAIL | Witness rejected: `Num2Bits(7)`, since −5 is p − 5 in the field |

For the PASS cases, the runner also ran `wtns check` against the R1CS, generated a Groth16 proof, and verified it. Each result comes from the snarkjs process exit code.

**Invalid cases** are rejected during witness generation. The circom witness calculator evaluates every `===` constraint as an assertion, so no satisfying witness exists and no proof can be produced from these inputs.

---

## 11. Tampering Test (executed)

1. Generated and verified a proof for (65, 75, 10): `OK!`.
2. Edited a copy of `public.json` after proof generation and re-ran `groth16 verify` with the original proof:

| Altered input | Original → tampered | Verify exit | Result |
|---------------|---------------------|-------------|--------|
| score_v2 | `["65","75","10"]` → `["65","82","10"]` | 1 | `Invalid proof` (rejected) |
| delta | `["65","75","10"]` → `["65","75","9"]` | 1 | `Invalid proof` (rejected) |

The score_v2 tampering is notable because (65, 82, 10) is itself a true statement. The proof is still rejected because a proof is bound to the exact public inputs it was generated for.

---

## 12. Known Limitations

- **No version binding.** The proof does not tie scores to code versions. The backend must record which code produced which score, and that record is trusted.
- **Evaluator trust.** A dishonest evaluator can feed any in-range scores. The proof only shows that the supplied numbers satisfy the inequality.
- **No privacy.** All inputs are public.
- **Development trusted setup.** Single party; not production-safe (section 8).
- **Integer scores only.** Scores must be integers 0–100. The evaluator must round or scale before proving (for example, round to the nearest integer).
- **Adversarial witnesses not tested.** Invalid cases were tested through the circom witness calculator. No hand-crafted witness bypassing the calculator was tried. Soundness for such witnesses rests on the R1CS constraints listed in section 6.
- **No on-chain verification.** Verification is off-chain via snarkjs. The registry contract must not claim to verify proofs.

---

## 13. Display Guidelines

✅ Acceptable: "Groth16 proof verified: score_v2 (75) ≥ score_v1 (65) + delta (10). Scores are public; the proof does not bind them to code versions. Development trusted setup."

❌ Prohibited: "ZK proves the AI improved", "ZK proves the solution is correct", "ZK hides the scores", "production-grade proof".

---

**End of ZK Trust Model v6.0**
