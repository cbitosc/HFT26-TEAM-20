"""Documentation must not claim setup files or commands that do not exist, and the lifecycle it
describes must match the code. These tests read the real markdown files in the repository."""
import importlib
import importlib.util
import re
from pathlib import Path

import pytest

from app.config import BACKEND_DIR
from app.lifecycle import TERMINAL_STATUSES, ExecutionStatus

ROOT = BACKEND_DIR.parent
DOCS = sorted([ROOT / "README.md", ROOT / "SPEC.md", ROOT / "AGENTS.md", BACKEND_DIR / "README.md",
               *(ROOT / "docs").glob("*.md")])
# Historical records describe past states on purpose; they are not setup guidance.
HISTORICAL = {"AUDIT_REPORT.md", "CROSS_AGENT_EXPERIMENT.md"}
CURRENT_DOCS = [p for p in DOCS if p.name not in HISTORICAL]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fenced_blocks(text: str):
    return re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)


# ---- nonexistent files and commands ----------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "database/schema.sql",
    "schema.sql",
    "uvicorn main:app",
    "aiosqlite",
    "sqlite3 autoevolve.db",
    "pip install -r dashboard/requirements.txt",
    "npm install -g snarkjs",
])
def test_no_current_doc_claims_a_nonexistent_file_or_command(phrase):
    offenders = [p.relative_to(ROOT).as_posix() for p in CURRENT_DOCS if phrase in read(p)]
    # IMPLEMENTATION_PLAN mentions aiosqlite only to say it is NOT used
    if phrase == "aiosqlite":
        offenders = [o for o in offenders if o != "docs/IMPLEMENTATION_PLAN.md"]
    assert offenders == [], f"{phrase!r} still appears in {offenders}"


def test_implementation_plan_only_mentions_aiosqlite_to_say_it_is_unused():
    text = read(ROOT / "docs" / "IMPLEMENTATION_PLAN.md")
    for line in text.splitlines():
        if "aiosqlite" in line:
            assert "Not used" in line, line


def test_referenced_repository_files_exist():
    """Files that the setup instructions tell a user to use must exist (planned ones are not named as commands)."""
    must_exist = [
        "backend/requirements.txt", "backend/.env.example", "backend/README.md", "backend/pytest.ini",
        "backend/app/main.py", "backend/app/init_db.py",
        "zk/package.json", "zk/scripts/build.js", "zk/tests/run_tests.js", "zk/circuits/improvement_proof.circom",
    ]
    for rel in must_exist:
        assert (ROOT / rel).exists(), rel
    readme = read(ROOT / "README.md")
    for rel in ("backend/requirements.txt", "backend/.env.example", "zk/scripts/build.js", "zk/tests/run_tests.js"):
        assert rel.split("/")[-1] in readme


def test_uvicorn_targets_in_docs_resolve_to_a_real_app():
    targets = set()
    for p in CURRENT_DOCS:
        for block in fenced_blocks(read(p)):
            targets |= set(re.findall(r"uvicorn\s+([A-Za-z_][\w.]*:[A-Za-z_]\w*)", block))
    assert targets, "expected at least one documented uvicorn command"
    for target in targets:
        module, attr = target.split(":")
        assert hasattr(importlib.import_module(module), attr), f"{target} does not exist"


def test_python_module_commands_in_docs_exist():
    modules = set()
    for p in CURRENT_DOCS:
        for block in fenced_blocks(read(p)):
            modules |= set(re.findall(r"python(?:\.exe)?\s+-m\s+([A-Za-z_][\w.]*)", block))
    third_party_or_stdlib = {"pip", "venv", "pytest", "uvicorn"}
    for module in modules - third_party_or_stdlib:
        assert importlib.util.find_spec(module) is not None, f"python -m {module} does not exist"
    assert "app.init_db" in modules  # the documented init command is covered


def test_requirements_files_named_in_docs_exist():
    for p in CURRENT_DOCS:
        for block in fenced_blocks(read(p)):
            for path in re.findall(r"-r\s+(\S+requirements\.txt)", block):
                candidates = [ROOT / path, BACKEND_DIR / path]
                assert any(c.exists() for c in candidates), f"{p.name}: {path} does not exist"


def test_the_database_is_documented_as_created_automatically():
    readme = read(ROOT / "README.md")
    assert "no SQL schema file" in readme.lower() or "There is no SQL schema file" in readme
    assert "create_all" in readme


# ---- implemented / planned distinction -------------------------------------------------------
def test_readme_separates_implemented_from_planned():
    readme = read(ROOT / "README.md")
    for token in ("Implemented", "Not yet implemented", "Planned"):
        assert token in readme
    assert "Current Implementation Status" in readme


def test_unimplemented_components_are_not_described_as_existing_in_setup():
    readme = read(ROOT / "README.md")
    setup = readme.split("## 7. Setup Instructions")[1].split("## 8. API Endpoints")[0]
    for planned in ("streamlit run", "foundryup", "forge ", "dashboard/"):
        assert planned not in setup.replace("(no setup exists yet)", ""), planned
    assert "7.3 Planned" in setup


def test_spec_and_plan_state_what_is_implemented():
    assert "[planned]" in read(ROOT / "SPEC.md")
    assert "Not yet implemented" in read(ROOT / "docs" / "IMPLEMENTATION_PLAN.md")
    assert "docs/API_CONTRACT.md" in read(ROOT / "SPEC.md")  # section 5 defers to the real contract


def test_valid_planned_features_were_not_deleted():
    """The correction must label planned work, not remove it."""
    spec = read(ROOT / "SPEC.md")
    for planned in ("AutoEvolveRegistry", "Streamlit", "Pinata", "Sepolia", "snarkjs", "Cross-Agent Memory"):
        assert planned in spec, planned


# ---- lifecycle consistency with the code -----------------------------------------------------
LIFECYCLE_DOCS = [ROOT / "docs" / "API_CONTRACT.md", ROOT / "docs" / "ARCHITECTURE.md", BACKEND_DIR / "README.md"]


@pytest.mark.parametrize("path", LIFECYCLE_DOCS, ids=lambda p: p.name)
def test_every_terminal_state_in_the_code_is_documented(path):
    text = read(path)
    for status in TERMINAL_STATUSES:
        assert f"`{status.value}`" in text, f"{path.name} does not mention `{status.value}`"


@pytest.mark.parametrize("path", [ROOT / "docs" / "API_CONTRACT.md", ROOT / "docs" / "ARCHITECTURE.md"], ids=lambda p: p.name)
def test_every_lifecycle_state_is_documented(path):
    text = read(path)
    missing = [s.value for s in ExecutionStatus if s.value not in text]
    assert missing == [], f"{path.name} is missing {missing}"


def test_documented_terminal_list_matches_the_code():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    sentence = next(s for s in api.split("\n") if "are terminal and have no outgoing transitions" in s)
    documented = set(re.findall(r"`(\w+)`", sentence.split("are terminal")[0].split("reachable from every non-terminal state.")[-1]))
    assert documented == {s.value for s in TERMINAL_STATUSES}


def test_api_contract_documents_the_new_field_and_state_semantics():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    assert "max_revisions" in api
    assert "completed_no_improvement" in api
    assert "not a failure" in api.lower()
    assert "ck_evaluations_overall_consistent" in api


def test_docs_do_not_claim_clients_can_submit_scores_or_decisions():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    assert "no** endpoint for clients to create or modify versions, evaluations" in api
    readme = read(ROOT / "README.md")
    assert "no endpoint for clients to submit evaluation scores" in readme


# ---- evaluation engine and acceptance policy (Milestone 06 / PRD alignment) -------------------
def test_evaluation_doc_states_the_security_limitation_and_the_trust_limits():
    text = read(ROOT / "docs" / "EVALUATION_ENGINE.md")
    assert "NOT a security sandbox" in text
    for statement in ("A weak suite can approve buggy code", "The evaluator is trusted", "advisory",
                      "bound to the SHA-256 of the exact code", "does not show that the evaluator ran honestly",
                      "proves only `score_v2 >= score_v1 + delta`"):
        assert statement in text, statement


def test_documented_delta_rule_version_and_terms_match_the_code():
    from app.evaluation import policy

    text = read(ROOT / "docs" / "EVALUATION_ENGINE.md")
    assert f"Delta = {policy.DELTA}" in text and f"rule version {policy.SCORING_RULE_VERSION}" in text
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    for term in (*policy.PRECONDITIONS, *policy.PREDICATE_TERMS):
        assert f"`{term}`" in text and f"`{term}`" in api, term
    for status in ("validated_improvement", "rejected_attempt", "invalid_comparison", "unvalidated_proposal"):
        assert status in text and status in api


def test_every_api_route_is_documented_in_the_contract():
    from app.main import create_app
    from app.config import Settings

    app = create_app(Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:"))
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    routes = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/")}
    missing = sorted(p for p in routes if f"`{p}`" not in api and f"{p}`" not in api)
    assert missing == [], missing


def test_docs_say_hidden_tests_are_never_revealed_and_the_dashboard_is_react():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    assert "Hidden tests are never revealed" in api
    assert "React" in read(ROOT / "AGENTS.md") and "React" in read(ROOT / "docs" / "PRD_ALIGNMENT.md")
    assert "Superseded" in read(ROOT / "docs" / "DASHBOARD_SPEC.md")


def test_new_settings_are_in_the_env_example():
    example = read(BACKEND_DIR / ".env.example")
    for name in ("EVALUATION_TIMEOUT_SECONDS", "EVALUATION_TOTAL_TIMEOUT_SECONDS", "ALLOW_UNSANDBOXED_EVALUATION"):
        assert name in example


def test_bundle_docs_state_what_is_never_exported_and_that_nothing_is_uploaded():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    engine = read(ROOT / "docs" / "EVALUATION_ENGINE.md")
    assert "Never in a bundle:" in api and "local only" in api
    assert "Nothing is uploaded" in engine and "counts only" in engine
    for code in ("CODE_HASH_MISMATCH", "EVIDENCE_NOT_EXPORTABLE", "EVIDENCE_BUNDLE_NOT_FOUND"):
        assert code in api, code


def test_run_concurrency_restart_and_budget_rules_are_documented_and_match_the_code():
    from app.config import Settings

    api = read(ROOT / "docs" / "API_CONTRACT.md")
    for text in ("RUN_ALREADY_STARTED", "not resumed automatically", '"stalled": true', "LLM_CALL_BUDGET_EXCEEDED",
                 "LLM_TOKEN_BUDGET_EXCEEDED", "compare-and-swap", "its own database session for every step"):
        assert text in api, text
    defaults = Settings(_env_file=None)
    assert f"default {defaults.llm_max_calls_per_execution}" in api
    assert f"default {defaults.llm_max_total_tokens_per_execution:,}" in api
    example = read(BACKEND_DIR / ".env.example")
    assert "LLM_MAX_CALLS_PER_EXECUTION" in example and "LLM_MAX_TOTAL_TOKENS_PER_EXECUTION" in example
    assert "not resumed" in read(ROOT / "docs" / "ARCHITECTURE.md")


def test_uploaded_suite_and_dashboard_docs_are_present_and_honest():
    api = read(ROOT / "docs" / "API_CONTRACT.md")
    for text in ("SUITE_UPLOAD_REJECTED", "HIDDEN_SUITE_UNAVAILABLE", "/api/dashboard/executions",
                 "/api/status", "ast.literal_eval", "encrypted at rest", "counts and hashes only"):
        assert text in api, text
    arch = read(ROOT / "docs" / "ARCHITECTURE.md")
    engine = read(ROOT / "docs" / "EVALUATION_ENGINE.md")
    # The key-on-host limitation must be stated plainly in both the architecture and the engine docs.
    assert "not protect against an attacker who already controls the host" in arch
    assert "not protection from a compromised host" in engine
    example = read(BACKEND_DIR / ".env.example")
    assert "HIDDEN_SUITE_KEY" in example and "CORS_ALLOWED_ORIGINS" in example


def test_env_example_never_contains_a_real_fernet_key():
    # The placeholder must be empty; a real key is 44 urlsafe-base64 chars ending in '='.
    for line in read(BACKEND_DIR / ".env.example").splitlines():
        if line.startswith("HIDDEN_SUITE_KEY="):
            assert line.strip() == "HIDDEN_SUITE_KEY="