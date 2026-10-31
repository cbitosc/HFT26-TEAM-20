"""Generator: writes candidate code. Untrusted. It sees the task and PUBLIC tests only.

For a revision it also sees the code of the current best version, that version's PUBLIC failures, a
validated Critic suggestion and lesson (if any) and, after a rejected attempt, the failed term ids.
It never sees hidden test ids, names, contents, per-test results or hidden counts.
"""
import re
from dataclasses import dataclass

from app.agents.context import PublicEvidence, render_public_failures, render_public_tests
from app.evaluation.suite import EvaluationSuite
from app.hashing import canonical_sha256
from app.llm.client import TEMPERATURE, LLMClient, LLMResponse

SYSTEM = (
    "You are the Generator in AutoEvolve. Write a complete, standalone Python module that solves the "
    "task. Reply with exactly one fenced code block (```python ... ```) and nothing else. Your code will be "
    "run against tests you have not seen; only the public tests are shown to you."
)
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.S)


class GeneratorOutputError(Exception):
    code = "GENERATOR_OUTPUT_INVALID"


@dataclass(frozen=True)
class RevisionContext:
    base_label: str
    base_code: str
    evidence: PublicEvidence
    critic_suggestion: str | None = None
    critic_lesson: str | None = None
    rejected_terms: tuple[str, ...] = ()  # term ids of a rejected attempt (no messages: they carry hidden counts)


@dataclass(frozen=True)
class Generation:
    code: str
    response: LLMResponse
    prompt_sha256: str


def build_prompt(task, suite: EvaluationSuite, revision: RevisionContext | None = None) -> str:
    parts = [
        f"Task: {task.title}",
        f"Description:\n{task.description}",
        "Requirements:\n" + ("\n".join(f"- {r}" for r in task.requirements) or "(none)"),
        f"Language: {task.language or suite.language}",
        f"Required entry point: a module-level function `{suite.entrypoint}` taking "
        f"{suite.contract.arity} positional argument(s).",
        f"Public tests:\n{render_public_tests(suite)}",
    ]
    if task.starter_code:
        parts.append(f"Starter code:\n```python\n{task.starter_code}\n```")
    if revision is not None:
        parts.append(f"Current best version ({revision.base_label}):\n```python\n{revision.base_code}\n```")
        parts.append(f"Evaluator results for {revision.base_label} (public tests):\n"
                     f"{render_public_failures(revision.evidence)}")
        if revision.rejected_terms:
            parts.append("A previous revision was rejected by the acceptance gate. Failed terms: "
                         + ", ".join(revision.rejected_terms) + ".")
        if revision.critic_suggestion:
            parts.append(f"Reviewer suggestion (advisory, may be wrong):\n{revision.critic_suggestion}")
        if revision.critic_lesson:
            parts.append(f"Reviewer lesson (advisory, may be wrong):\n{revision.critic_lesson}")
        parts.append("Write an improved version. Keep everything that already works.")
    return "\n\n".join(parts)


def prompt_hash(model: str, system: str, user: str) -> str:
    return canonical_sha256({"model": model, "temperature": TEMPERATURE, "system": system, "user": user})


def extract_code(text: str, max_chars: int) -> str:
    """The first fenced block (preferring one labelled python). Empty or oversized output is rejected."""
    blocks = _FENCE.findall(text or "")
    if not blocks:
        raise GeneratorOutputError("the Generator reply contains no fenced code block")
    python = [body for lang, body in blocks if lang.lower() in ("python", "py")]
    code = (python or [blocks[0][1]])[0].strip("\r\n")
    if not code.strip():
        raise GeneratorOutputError("the Generator returned an empty code block")
    if len(code) > max_chars:
        raise GeneratorOutputError(f"the Generator returned {len(code)} characters of code (limit {max_chars})")
    return code + "\n"


def generate(llm: LLMClient, model: str, user_prompt: str, max_chars: int) -> Generation:
    response = llm.complete(model=model, system=SYSTEM, user=user_prompt)
    return Generation(extract_code(response.text, max_chars), response, prompt_hash(model, SYSTEM, user_prompt))
