pragma circom 2.0.0;

// AutoEvolve Protocol - ImprovementProof
//
// Claim proven (and nothing more):
//     0 <= score_v1 <= 100
//     0 <= score_v2 <= 100
//     1 <= delta    <= 50
//     score_v2 >= score_v1 + delta      (equality passes)
//
// All three values are PUBLIC inputs. The proof does not hide them, does not
// bind them to any source-code version, and says nothing about evaluator
// honesty, code correctness, or the quality of any LLM output.
//
// Soundness note (circomlib 2.0.5): LessThan(n) is only sound when both of its
// inputs are < 2^n. LessEqThan(n) calls LessThan(n) with (in[0], in[1] + 1),
// and GreaterThan(n) calls LessThan(n) with (in[1], in[0]). The Num2Bits range
// checks below guarantee these preconditions for every comparator used.

include "../node_modules/circomlib/circuits/bitify.circom";
include "../node_modules/circomlib/circuits/comparators.circom";

template ImprovementProof() {
    signal input score_v1;
    signal input score_v2;
    signal input delta;

    // ---- score_v1: 0 <= score_v1 <= 100 ----
    // Num2Bits(7) forces 0 <= score_v1 < 128 (rejects negatives / field wrap).
    component v1Bits = Num2Bits(7);
    v1Bits.in <== score_v1;
    // LessThan(7) inputs: score_v1 < 128, 100 + 1 = 101 < 128.
    component v1Le100 = LessEqThan(7);
    v1Le100.in[0] <== score_v1;
    v1Le100.in[1] <== 100;
    v1Le100.out === 1;

    // ---- score_v2: 0 <= score_v2 <= 100 ----
    component v2Bits = Num2Bits(7);
    v2Bits.in <== score_v2;
    component v2Le100 = LessEqThan(7);
    v2Le100.in[0] <== score_v2;
    v2Le100.in[1] <== 100;
    v2Le100.out === 1;

    // ---- delta: 1 <= delta <= 50 ----
    // Num2Bits(6) forces 0 <= delta < 64.
    component deltaBits = Num2Bits(6);
    deltaBits.in <== delta;
    // LessThan(6) inputs: delta < 64, 50 + 1 = 51 < 64.
    component deltaLe50 = LessEqThan(6);
    deltaLe50.in[0] <== delta;
    deltaLe50.in[1] <== 50;
    deltaLe50.out === 1;
    // GreaterThan(6) -> LessThan(6) with (0, delta); both < 64.
    component deltaGt0 = GreaterThan(6);
    deltaGt0.in[0] <== delta;
    deltaGt0.in[1] <== 0;
    deltaGt0.out === 1;

    // ---- Main claim: target <= score_v2, i.e. score_v2 >= score_v1 + delta ----
    // No subtraction is performed, so there is no field underflow.
    // target <= 100 + 50 = 150 given the checks above (and < 128 + 64 = 192
    // from Num2Bits alone), so target < 256 and score_v2 + 1 <= 101 < 256,
    // which satisfies the LessThan(8) precondition. A separate
    // "target <= 150" constraint would be redundant and is omitted.
    signal target;
    target <== score_v1 + delta;

    component mainClaim = LessEqThan(8);
    mainClaim.in[0] <== target;
    mainClaim.in[1] <== score_v2;
    mainClaim.out === 1;
}

component main {public [score_v1, score_v2, delta]} = ImprovementProof();
