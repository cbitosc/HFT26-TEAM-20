# AutoEvolve — Judge Demo Runbook

**What this demo shows:** an AI agent's claim of improvement is never trusted. A deterministic evaluator
measures every version, a strict gate decides acceptance, and every result becomes typed, tamper-evident
evidence. Developers can bring their own hidden tests, which are encrypted and never leak.

**What is real vs. scripted (say this out loud):**

| Real, running in the demo | Standing in |
|---|---|
| Deterministic evaluator (runs code against public + hidden tests) | The **Generator / Critic**: a scripted stand-in returns prepared candidate code. No live Featherless run has been validated yet. |
| Strict acceptance gate (no LLM in scoring or acceptance) | |
| Typed evidence + hash-addressed bundles | |
| Sealed hidden-test upload (encrypted at rest) | |
| Every dashboard/API response | |

Nothing is faked in the part that is the contribution. The scripted generator just removes a flaky,
billed network call from a live demo; swap in the real model later with one config change.

---

## Option A — the one-command story (recommended)

```powershell
cd C:\Users\ASUS\Desktop\CBIT
backend\.venv\Scripts\python.exe eval\demo.py          # add --pause to stop between acts
```

It runs the whole pipeline over the real HTTP API and prints real JSON, in 7 acts (~2 seconds, no network):

1. **Status** — what the system reports about itself (booleans only; no key or model id).
2. **Sealed upload** — a developer uploads public *and* hidden tests; the response shows counts and
   hashes only, and the printed check confirms no hidden value leaked.
3. **Start a run** — submit the merge-intervals task; the **commitment** (suite hashes, evaluator config,
   scoring rule, delta) is recorded *before* any code is generated.
4. **Evolution tree** — V1 (scripted flawed code) scores hidden 2/10; V2 scores hidden 9/10; the gate
   **accepts** V2 (strict improvement, no regression). Best hidden accuracy 90%.
5. **Evidence + bundle** — a `validated_improvement` record, exported as a bundle with a SHA-256 that is
   re-verified on read (`hash_valid=true`).
6. **Negative evidence** — a second run where V2 fixes a public test but breaks a hidden one. The gate
   **rejects** it and records exactly why, in hidden-safe terms:
   `no_test_regression: 1 hidden test(s) passed in V1 but fail in V2` and `aggregate_delta`.
7. **Privacy proof** — all 10 hidden test ids are searched across the tree, evidence, bundle and the
   dashboard list: zero hits.

**The single most important line for judges** is in Act 6: the system can tell a developer *why* a
"better-looking" revision was refused, without ever revealing the hidden tests.

---

## Option B — interactive API (if a judge wants to click)

Start the server, then open the auto-generated API docs:

```powershell
cd C:\Users\ASUS\Desktop\CBIT\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# browser: http://127.0.0.1:8000/docs
```

Good endpoints to open live: `GET /api/status`, `POST /api/tasks` (try an inline `suite`),
`GET /api/dashboard/executions`, `GET /api/executions/{id}/tree`, `GET /api/executions/{id}/evidence`.
Note: a full *run* through `/docs` needs a real `FEATHERLESS_API_KEY`; use Option A to avoid that.

---

## Option C — prove the rigour (for a technical judge)

```powershell
cd C:\Users\ASUS\Desktop\CBIT\backend
.venv\Scripts\python.exe -m pytest -q          # 600 tests pass
```

Mention: besides the tests, a *mutation check* deliberately breaks each security rule (leak a hidden id,
store plaintext, log the key, accept executable test input, wildcard CORS, skip the gate) and confirms a
test catches every one.

---

## The 60-second script to say

1. "AI agents claim they improved. We don't take the claim — we measure it."
2. "Here's a task with public tests the agent sees and hidden tests it never sees." (Act 2/3)
3. "V1 fails. The agent revises. Our evaluator scores V2 on the hidden suite, and a strict gate accepts
   it only because it strictly improved and broke nothing." (Act 4)
4. "Every decision is evidence with a hash you can verify." (Act 5)
5. "And when a revision looks better but breaks a hidden test, we reject it and say exactly why —
   without leaking the hidden test." (Act 6/7)

---

## Honest limits to state before they ask

- The **Generator/Critic are scripted** in this demo; a live model run has not been validated.
- The **ZK proof** exists as a standalone prototype and is **not wired into** the pipeline.
- **Publishing** (IPFS/Pinata, Sepolia) is not built; the status endpoint says `publishing: not available`.
- Hidden tests are **encrypted at rest**; the key lives on the evaluator's host, so this is not protection
  from a compromised host. During a run the decrypted suite is written to a temp dir and deleted after.
- There is **no web UI yet**; this demo is the backend over HTTP.
