// Build the ImprovementProof circuit and run a DEVELOPMENT-ONLY Groth16 setup.
//
// WARNING: this is a single-party local trusted setup. Whoever runs it could in
// principle keep the toxic waste and forge proofs. It is suitable for a
// hackathon prototype only. Production use requires a multi-party ceremony
// (e.g. a public Powers of Tau file plus an independent phase-2 ceremony).
//
// Usage (from zk/):  node scripts/build.js

const { execFileSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const ZK = path.resolve(__dirname, "..");
const BUILD = path.join(ZK, "build");
const CIRCOM = path.join(ZK, "bin", process.platform === "win32" ? "circom.exe" : "circom");
const SNARKJS = path.join(ZK, "node_modules", "snarkjs", "build", "cli.cjs");
const NAME = "improvement_proof";
const PTAU_POWER = 8; // 2^8 = 256 >= 82 constraints + public inputs

function run(label, cmd, args) {
  console.log(`\n=== ${label} ===`);
  execFileSync(cmd, args, { cwd: ZK, stdio: "inherit" });
}
const snark = (label, ...args) => run(label, process.execPath, [SNARKJS, ...args]);
// Entropy is generated in-process and never printed.
const entropy = () => crypto.randomBytes(32).toString("hex");
const b = (f) => path.join(BUILD, f);

fs.mkdirSync(BUILD, { recursive: true });

run("Compile circuit", CIRCOM, [
  path.join(ZK, "circuits", `${NAME}.circom`),
  "--r1cs", "--wasm", "--sym", "--inspect", "-o", BUILD,
]);
snark("R1CS info", "r1cs", "info", b(`${NAME}.r1cs`));

snark("Powers of Tau: new (bn128)", "powersoftau", "new", "bn128", String(PTAU_POWER), b("pot_0000.ptau"));
snark("Powers of Tau: contribute (dev)", "powersoftau", "contribute", b("pot_0000.ptau"), b("pot_0001.ptau"),
  "--name=autoevolve-dev-1", "-e=" + entropy());
snark("Powers of Tau: prepare phase 2", "powersoftau", "prepare", "phase2", b("pot_0001.ptau"), b("pot_final.ptau"));
snark("Powers of Tau: verify", "powersoftau", "verify", b("pot_final.ptau"));

snark("Groth16 setup", "groth16", "setup", b(`${NAME}.r1cs`), b("pot_final.ptau"), b(`${NAME}_0000.zkey`));
snark("zkey contribute (dev)", "zkey", "contribute", b(`${NAME}_0000.zkey`), b(`${NAME}_final.zkey`),
  "--name=autoevolve-dev-2", "-e=" + entropy());
snark("zkey verify", "zkey", "verify", b(`${NAME}.r1cs`), b("pot_final.ptau"), b(`${NAME}_final.zkey`));
snark("Export verification key", "zkey", "export", "verificationkey", b(`${NAME}_final.zkey`), b("verification_key.json"));

console.log("\nBuild complete (DEVELOPMENT-ONLY trusted setup).");
