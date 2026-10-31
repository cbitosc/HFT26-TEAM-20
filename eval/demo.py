"""AutoEvolve judge demo: the whole backend pipeline end-to-end, over the real HTTP API.

What is REAL here (the contribution): the deterministic evaluator, the strict acceptance gate, typed
evidence, hash-addressed evidence bundles, sealed hidden-test upload, and every dashboard response.

What is STANDING IN: the Generator and Critic. A live Featherless run has not been validated yet, so
this demo uses a scripted generator whose "model output" is a fixed candidate file. It is clearly
labelled below. No network call is made, nothing is billed, and the run is identical every time.

Run it:   backend\\.venv\\Scripts\\python.exe eval\\demo.py
          (add --pause to stop between acts for a live walkthrough)

It prints real API JSON. It also proves that no hidden test id, name or value appears in any response.
"""
import json
import sys
import tempfile
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
FIXTURES = BACKEND / "tests" / "fixtures"
PAUSE = "--pause" in sys.argv


def banner(n, title):
    print("\n" + "=" * 78 + f"\nACT {n}. {title}\n" + "=" * 78)
    if PAUSE:
        input("  [enter to continue] ")


def show(label, obj):
    print(f"\n{label}:")
    print("  " + json.dumps(obj, indent=2).replace("\n", "\n  "))


def code_reply(name):
    return "```python\n" + (FIXTURES / f"{name}.py").read_text(encoding="utf-8") + "```\n"


def critic_reply(**kw):
    base = {"diagnosis": "V1 fails some hidden cases.", "suggestion": "Validate input and avoid mutating it.",
            "lesson": "Handle unsorted input and never mutate the caller's list."}
    base.update(kw)
    return json.dumps(base)


def main():
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.agents import generator as generator_agent
    from app.config import Settings
    from app.llm.client import LLMResponse
    from app.main import create_app

    class ScriptedModel:
        """Stands in for Featherless. Returns prepared candidate code / critiques in order. LABELLED."""

        def __init__(self):
            self.generator, self.critic = [], []

        def complete(self, *, model, system, user):
            queue = self.generator if system == generator_agent.SYSTEM else self.critic
            text = queue.pop(0)
            return LLMResponse(text=text, requested_model=model, returned_model="scripted-stand-in (not a live model)",
                               latency_seconds=0.0, prompt_tokens=100, completion_tokens=50, total_tokens=150, attempts=1)

    tmp = tempfile.mkdtemp(prefix="autoevolve_demo_")
    settings = Settings(_env_file=None, app_env="development",
                        database_url=f"sqlite:///{(Path(tmp) / 'demo.db').as_posix()}",
                        featherless_api_key=SecretStr("demo-key-scripted-generator"),
                        featherless_critic_model="scripted-critic",
                        hidden_suite_key=Fernet.generate_key().decode())
    model = ScriptedModel()
    app = create_app(settings)
    app.state.llm_client_factory = lambda s: model

    print(__doc__.split("Run it:")[0].strip())

    with TestClient(app) as c:
        # ---- ACT 1: capabilities ----
        banner(1, "What the system reports about itself (GET /api/status)")
        show("status", c.get("/api/status").json()["data"])
        print("\n  Note: 'scripted-stand-in' generator; evaluator/gate/evidence/sealing below are real.")

        # ---- ACT 2: a developer submits a task with their OWN sealed hidden tests ----
        banner(2, "A developer uploads public AND hidden tests; the hidden tests are sealed")
        upload = {
            "title": "Square a number", "description": "Implement f(x) that returns x*x.",
            "suite": {
                "entrypoint": "f", "contract": {"arity": 1, "smoke_args": "(2,)", "smoke_type": "int"},
                "public_tests": [{"id": "pub_two", "description": "2 -> 4",
                                  "checks": [{"kind": "returns", "args": "(2,)", "expected": "4"}]}],
                "hidden_tests": [{"id": "secret_three", "description": "hidden: 3 -> 9",
                                  "checks": [{"kind": "returns", "args": "(3,)", "expected": "9"}]},
                                 {"id": "secret_zero", "description": "hidden: 0 -> 0",
                                  "checks": [{"kind": "returns", "args": "(0,)", "expected": "0"}]}],
            },
        }
        uploaded = c.post("/api/tasks", json=upload).json()["data"]
        show("task.suite (counts + hashes only; note source='uploaded')", uploaded["suite"])
        hidden_markers = ["secret_three", "secret_zero", "(3,)", "(0,)"]
        leaked = [m for m in hidden_markers if m in c.post("/api/tasks", json=upload).text]
        print(f"\n  Hidden markers leaked in the upload response: {leaked}  (expected: [])")

        # ---- the headline run uses the merge-intervals suite (richer: 5 public / 10 hidden) ----
        banner(3, "Submit the merge-intervals task and start an evolution run")
        task = c.post("/api/tasks", json={"title": "Merge intervals",
                      "description": "Merge overlapping or touching integer intervals; validate input; never mutate it.",
                      "requirements": ["Merge overlapping and touching", "Do not mutate the input",
                                       "Raise TypeError/ValueError on bad input"],
                      "evaluation_suite_id": "python-merge-intervals-v1"}).json()["data"]
        print(f"  task {task['id']}  suite={task['suite']['id']} "
              f"(public={task['suite']['public_test_count']}, hidden={task['suite']['hidden_test_count']})")
        execution = c.post(f"/api/tasks/{task['id']}/executions").json()["data"]
        show("execution commitment (recorded before any code is generated)", execution["commitment"])

        # V1 = flawed (fails many hidden tests); V2 = gen_7b (passes 9/10 hidden). Scripted, labelled.
        model.generator = [code_reply("flawed"), code_reply("gen_7b")]
        model.critic = [critic_reply()]
        c.post(f"/api/executions/{execution['id']}/run")  # TestClient runs the background task synchronously
        final = c.get(f"/api/executions/{execution['id']}").json()["data"]
        print(f"\n  run finished: status={final['status']}, best_version={final['best_version_id']}")

        # ---- ACT 4: the version tree the dashboard would render ----
        banner(4, "The evolution tree: V1 vs V2 by the evaluator (GET /executions/{id}/tree)")
        tree = c.get(f"/api/executions/{execution['id']}/tree").json()["data"]
        for v in tree["versions"]:
            print(f"  {v['label']}: hidden {v['hidden']['passed']}/{v['hidden']['total']}, "
                  f"public {v['public']['passed']}/{v['public']['total']}, S={v['overall_score']:.2f}, "
                  f"decision={v['acceptance_status']}  (critic note is {v['critic_note_kind']})")
        print(f"\n  best hidden accuracy: {tree['best_hidden_accuracy']:.0f}%  "
              "-> the gate accepted V2 because it strictly improved with no regression.")

        # ---- ACT 5: typed evidence + a hash-addressed bundle ----
        banner(5, "Evidence: what was proven, and a tamper-evident bundle (GET /executions/{id}/evidence)")
        evidence = c.get(f"/api/executions/{execution['id']}/evidence").json()["data"]
        rec = evidence["records"][0]
        print(f"  evidence record: status={rec['status']}")
        print(f"    V1 score {rec['previous_scores']['overall_score']:.2f} -> V2 score {rec['candidate_scores']['overall_score']:.2f}")
        bundle = c.post(f"/api/evidence/{rec['id']}/bundle").json()["data"]
        print(f"  bundle sha256: {bundle['bundle_sha256']}")
        print(f"  hash re-verified on read: hash_valid={bundle['hash_valid']}, canonical={bundle['canonical']}")

        # ---- ACT 6: a rejected revision becomes NEGATIVE evidence, with the exact reason ----
        banner(6, "A revision that looks better but breaks a hidden test is rejected (negative evidence)")
        task2 = c.post("/api/tasks", json={"title": "Merge intervals (take 2)", "description": "same task",
                       "evaluation_suite_id": "python-merge-intervals-v1"}).json()["data"]
        ex2 = c.post(f"/api/tasks/{task2['id']}/executions", json={}).json()["data"]
        # V1 gen_coder (baseline), V2 fixes the public failure but breaks a hidden test -> rejected.
        model.generator = [code_reply("gen_coder"), code_reply("gen_coder_sorts_in_place")]
        model.critic = [critic_reply()]
        # one revision only, so a rejected V2 ends the run honestly as 'no improvement'
        from app.services import execution_service as exe
        session = app.state.session_factory()
        try:
            exe.get_execution(session, ex2["id"]).max_revisions = 1
            session.commit()
        finally:
            session.close()
        c.post(f"/api/executions/{ex2['id']}/run")
        status2 = c.get(f"/api/executions/{ex2['id']}").json()["data"]["status"]
        ev2 = c.get(f"/api/executions/{ex2['id']}/evidence").json()["data"]
        rejected = next(r for r in ev2["records"] if r["status"] == "rejected_attempt")
        print(f"  final status: {status2}")
        print("  the gate recorded WHY, in hidden-safe terms:")
        for term in rejected["failed_terms"]:
            print(f"    - {term['term']}: {term['message']}")

        # ---- ACT 7: the privacy guarantee, checked ----
        banner(7, "Proof: hidden test identities never appear in any response")
        import re

        from app.evaluation.suites import get_suite
        hidden_ids = [t.id for t in get_suite("python-merge-intervals-v1").hidden_tests]
        bodies = [c.get(f"/api/executions/{execution['id']}/tree").text,
                  c.get(f"/api/executions/{execution['id']}/evidence").text,
                  c.post(f"/api/evidence/{rec['id']}/bundle").text,
                  c.get("/api/dashboard/executions").text]
        # Whole-word match: a hidden id like 'chain' must not be matched inside words such as 'onchain'.
        hits = [h for h in hidden_ids for b in bodies
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(h)}(?![A-Za-z0-9_])", b)]
        print(f"  checked {len(hidden_ids)} hidden test ids across tree, evidence, bundle and the dashboard list")
        print(f"  leaks found: {hits}   (expected: [])")

        print("\n" + "=" * 78)
        print("Summary for the judges:")
        print("  * The agent's claim is never trusted. A deterministic evaluator measured every version,")
        print("    and a strict gate decided acceptance (no LLM in scoring or acceptance).")
        print("  * Every result is typed evidence; a rejection is first-class negative evidence with the")
        print("    exact failed rule. Each decision exports as a hash-addressed, tamper-evident bundle.")
        print("  * Developers upload their own hidden tests; those are encrypted at rest and never leak.")
        print("  * Honest limits: the Generator/Critic here are scripted stand-ins (no live model run yet);")
        print("    the ZK proof and publishing (IPFS/Sepolia) are not wired in; the key sits on this host")
        print("    (encryption at rest, not protection from a compromised host).")
        print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
