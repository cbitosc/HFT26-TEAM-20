// ImprovementProof test runner.
// Requires a prior `node scripts/build.js`. Every result below comes from real
// snarkjs process exit codes; nothing is hardcoded as passing.
//
// Usage (from zk/):  node tests/run_tests.js

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ZK = path.resolve(__dirname, "..");
const BUILD = path.join(ZK, "build");
const OUT = path.join(BUILD, "test_runs");
const SNARKJS = path.join(ZK, "node_modules", "snarkjs", "build", "cli.cjs");
const WASM = path.join(BUILD, "improvement_proof_js", "improvement_proof.wasm");
const R1CS = path.join(BUILD, "improvement_proof.r1cs");
const ZKEY = path.join(BUILD, "improvement_proof_final.zkey");
const VKEY = path.join(BUILD, "verification_key.json");

const CASES = [
  // [id, score_v1, score_v2, delta, expected]
  [1, 65, 82, 10, "PASS"],
  [2, 65, 75, 10, "PASS"],
  [3, 65, 74, 10, "FAIL"],
  [4, 82, 65, 10, "FAIL"],
  [5, 0, 100, 50, "PASS"],
  [6, 100, 100, 1, "FAIL"],
  [7, 65, 150, 10, "FAIL"],
  [8, 65, 80, 0, "FAIL"],
  [9, 65, 80, 51, "FAIL"],
  [10, -5, 50, 10, "FAIL"],
];

function snark(...args) {
  const r = spawnSync(process.execPath, [SNARKJS, ...args], { cwd: ZK, encoding: "utf8" });
  return { code: r.status, out: `${r.stdout || ""}${r.stderr || ""}` };
}

function firstErrorLine(text) {
  const line = text.split(/\r?\n/).find((l) => /error|assert|fail|invalid/i.test(l));
  return (line || text.trim().split(/\r?\n/).pop() || "").trim().slice(0, 140);
}

// Runs witness -> constraint check -> prove -> verify. Returns a result object.
function runCase(id, v1, v2, d) {
  const dir = path.join(OUT, `case_${id}`);
  fs.mkdirSync(dir, { recursive: true });
  const f = (n) => path.join(dir, n);
  fs.writeFileSync(f("input.json"), JSON.stringify({ score_v1: String(v1), score_v2: String(v2), delta: String(d) }));

  const w = snark("wtns", "calculate", WASM, f("input.json"), f("witness.wtns"));
  if (w.code !== 0) return { actual: "FAIL", stage: "witness rejected", detail: firstErrorLine(w.out) };

  const c = snark("wtns", "check", R1CS, f("witness.wtns"));
  if (c.code !== 0) return { actual: "FAIL", stage: "R1CS check failed", detail: firstErrorLine(c.out) };

  const p = snark("groth16", "prove", ZKEY, f("witness.wtns"), f("proof.json"), f("public.json"));
  if (p.code !== 0) return { actual: "FAIL", stage: "prove failed", detail: firstErrorLine(p.out) };

  const v = snark("groth16", "verify", VKEY, f("public.json"), f("proof.json"));
  const ok = v.code === 0 && /OK!/.test(v.out);
  return {
    actual: ok ? "PASS" : "FAIL",
    stage: ok ? "proof verified" : "verify rejected",
    detail: `public=${JSON.stringify(JSON.parse(fs.readFileSync(f("public.json"), "utf8")))}`,
    dir,
  };
}

function tamperTest(baseDir, label, mutate) {
  const pub = JSON.parse(fs.readFileSync(path.join(baseDir, "public.json"), "utf8"));
  const tampered = mutate([...pub]);
  const tPath = path.join(baseDir, `public_tampered_${label}.json`);
  fs.writeFileSync(tPath, JSON.stringify(tampered));
  const v = snark("groth16", "verify", VKEY, tPath, path.join(baseDir, "proof.json"));
  const accepted = v.code === 0 && /OK!/.test(v.out);
  return { label, original: pub, tampered, accepted, exit: v.code, detail: firstErrorLine(v.out) };
}

function main() {
  for (const p of [WASM, R1CS, ZKEY, VKEY]) {
    if (!fs.existsSync(p)) { console.error(`Missing ${p}. Run: node scripts/build.js`); process.exit(2); }
  }
  fs.rmSync(OUT, { recursive: true, force: true });

  let failures = 0;
  const results = {};
  console.log("ImprovementProof tests  (claim: score_v2 >= score_v1 + delta)\n");
  console.log("#  | v1  | v2  | d  | expected | actual | result | stage / detail");
  console.log("---|-----|-----|----|----------|--------|--------|---------------");
  for (const [id, v1, v2, d, expected] of CASES) {
    const r = runCase(id, v1, v2, d);
    results[id] = r;
    const match = r.actual === expected;
    if (!match) failures++;
    console.log(
      `${String(id).padEnd(2)} | ${String(v1).padStart(3)} | ${String(v2).padStart(3)} | ${String(d).padStart(2)} | ` +
      `${expected.padEnd(8)} | ${r.actual.padEnd(6)} | ${(match ? "OK" : "MISMATCH").padEnd(6)} | ${r.stage}: ${r.detail}`
    );
  }

  console.log("\nTampering test (valid proof for 65, 75, 10; public inputs altered afterwards)");
  const base = results[2];
  if (!base || base.actual !== "PASS") {
    console.log("  SKIPPED: case 2 did not produce a verified proof");
    failures++;
  } else {
    // public.json order follows the main declaration: [score_v1, score_v2, delta]
    const tampers = [
      tamperTest(base.dir, "score_v2", (s) => { s[1] = "82"; return s; }),
      tamperTest(base.dir, "delta", (s) => { s[2] = "9"; return s; }),
    ];
    for (const t of tampers) {
      if (t.accepted) failures++;
      console.log(
        `  ${t.label.padEnd(8)} ${JSON.stringify(t.original)} -> ${JSON.stringify(t.tampered)}: ` +
        `verify exit=${t.exit}, ${t.accepted ? "ACCEPTED (BAD)" : "REJECTED (expected)"} | ${t.detail}`
      );
    }
  }

  console.log(`\nSUMMARY: ${failures === 0 ? "ALL TESTS BEHAVED AS EXPECTED" : `${failures} UNEXPECTED RESULT(S)`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main();
