"""Prints the tables used in FEATHERLESS_CRITIC_VALIDATION_REPORT.md.
Reads the run file (measurements) and the judgments file (manual verdicts). No API calls.

Usage: python eval/critic_validation_summary.py [run_file.json]
"""
import glob
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
run_path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(R, "critic_validation_run_*.json")))[-1]
run = json.load(open(run_path, encoding="utf-8"))
judg = json.load(open(os.path.join(R, "critic_validation_judgments.json"), encoding="utf-8"))
reqs = run["requests"]
exp = run["evaluations"]["experiment"]
det = run["evaluations"]["model_details"]
price = {m: (float(d["pricing"]["prompt"]), float(d["pricing"]["completion"])) for m, d in det.items()}
short = lambda m: m.split("/")[-1]

print("run file:", os.path.basename(run_path))
print(f"requests={len(reqs)} non-200={sum(r['http_status'] != 200 for r in reqs)} "
      f"usage-missing={sum(r['total_tokens'] is None for r in reqs)} cost-missing={sum(r['reported_cost_usd'] is None for r in reqs)}")
worst = max(abs(r["prompt_tokens"] * price[r["model"]][0] + r["completion_tokens"] * price[r["model"]][1] - r["reported_cost_usd"]) for r in reqs)
print(f"max |tokens x listed price - reported cost| = ${worst:.10f}")
print(f"total reported cost = ${sum(r['reported_cost_usd'] for r in reqs):.6f}  (budget $1.00; worst-case bound ${run['evaluations']['cost_bound']['worst_case_usd']:.4f})")

print("\n-- per request: label | model | HTTP | latency_s | prompt | completion | finish | cost_usd")
for r in reqs:
    print(f"{r['label']:<22} {short(r['model']):<20} {r['http_status']} {r['latency_s']:>6.1f} {r['prompt_tokens']:>5} {r['completion_tokens']:>5} {r['finish_reason']:<5} {r['reported_cost_usd']:.8f}")

print("\n-- Critic requests, per model")
for m in ("Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-32B-Instruct"):
    rs = [r for r in reqs if r["role"] == "critic" and r["model"] == m]
    lat = [r["latency_s"] for r in rs]
    print(f"{short(m):<20} n={len(rs)} latency mean={st.mean(lat):.1f}s median={st.median(lat):.1f}s "
          f"| prompt={sum(r['prompt_tokens'] for r in rs)} completion={sum(r['completion_tokens'] for r in rs)} cost=${sum(r['reported_cost_usd'] for r in rs):.6f}")
rs = [r for r in reqs if r["role"] == "generator"]
print(f"{'revisions (7B gen)':<20} n={len(rs)} latency mean={st.mean(r['latency_s'] for r in rs):.1f}s "
      f"| prompt={sum(r['prompt_tokens'] for r in rs)} completion={sum(r['completion_tokens'] for r in rs)} cost=${sum(r['reported_cost_usd'] for r in rs):.6f}")

print("\n-- Automated aids (NOT correctness): strict_json / schema errors / contradictions flagged")
for c in exp["critics"]:
    print(f"{c['candidate']:<12} {c['tag']:<4} strict={c['strict_json']} schema_errors={len(c['schema_errors'])} "
          f"flagged_contradictions={len(c['contradictions'])} not_cited_failing={c['evidence_aids'].get('failing_tests_not_cited')}")

print("\n-- Manual verdict tallies")
tally = {}
for key, j in judg["critic_responses"].items():
    cand, tag = key.split("|")
    v = list(j["defects"].values())
    t = tally.setdefault((tag, "seeded" if cand.startswith("A") else "generated"),
                         {"TP": 0, "PARTIAL": 0, "FN": 0, "FP": 0, "contradicts": 0, "responses": 0, "conf_unjustified": 0, "harmful_or_regressing_fix": 0})
    t["TP"] += v.count("TP"); t["PARTIAL"] += v.count("PARTIAL"); t["FN"] += v.count("FN")
    t["FP"] += len(j["false_positives"]); t["responses"] += 1
    t["contradicts"] += int(j["contradicts_evaluator_evidence"]); t["conf_unjustified"] += int(not j["confidence_justified"])
    t["harmful_or_regressing_fix"] += sum(1 for f in j["fix"].values() if f.startswith(("harmful", "resolves")))
for (tag, kind), t in sorted(tally.items()):
    total = t["TP"] + t["PARTIAL"] + t["FN"]
    print(f"critic={tag:<4} candidates={kind:<9} defects={total}: TP={t['TP']} PARTIAL={t['PARTIAL']} FN={t['FN']} | "
          f"false_claims={t['FP']} contradicts_evaluator={t['contradicts']}/{t['responses']} "
          f"confidence_unjustified={t['conf_unjustified']}/{t['responses']} fixes_that_break_passing_tests={t['harmful_or_regressing_fix']}")

print("\n-- Revisions (Generator Qwen2.5-7B-Instruct fixed): candidate | variant | before -> after | fixed | regressed | identical")
for r in exp["revisions"]:
    print(f"{r['candidate']:<12} {r['variant']:<10} {r['before_passed']}/14 -> {r['after_passed']}/14 fixed={r['fixed_tests']} "
          f"regressed={r['regressed_tests']} identical={r['code_identical_to_original']} own_tests_exit={r['own_tests_exit']}")
print("\nprior 03.2 files unchanged:", exp["prior_files_unchanged"])
