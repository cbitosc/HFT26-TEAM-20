"""Critic: reads a candidate and the evaluator's PUBLIC evidence, proposes a diagnosis, a suggestion and
a lesson. Untrusted and advisory: its output is stored as critic_feedback (unvalidated_proposal) and is
never a score, a verdict or evidence. It sees hidden results as two COUNTS only, plus the gate's
failed-term messages (which name public tests and only count hidden ones). It never sees hidden test
ids, names or contents.
"""
import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.context import HiddenCounts, PublicEvidence, render_public_failures
from app.agents.generator import prompt_hash
from app.llm.client import LLMClient, LLMResponse

SYSTEM = (
    "You are the Critic in AutoEvolve. You review code against evaluator evidence. You do not score or "
    "approve anything. Reply with one JSON object and nothing else, with exactly these string fields: "
    '"diagnosis" (what is wrong, at most 2000 characters), "suggestion" (a concrete fix, at most 2000 '
    'characters), "lesson" (a short reusable lesson, at most 1000 characters).'
)
_OBJECT = re.compile(r"\{.*\}", re.S)


class CriticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    diagnosis: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(min_length=1, max_length=2000)
    lesson: str = Field(min_length=1, max_length=1000)


def build_prompt(label: str, code: str, evidence: PublicEvidence, hidden: HiddenCounts,
                 failed_terms: list[dict] | None = None) -> str:
    parts = [
        f"Candidate {label}:\n```python\n{code}\n```",
        f"Public test results:\n{render_public_failures(evidence)}",
        f"Hidden tests (not shown to anyone): {hidden.passed} of {hidden.total} pass.",
    ]
    if failed_terms:
        parts.append("The acceptance gate rejected this candidate. Failed terms:\n"
                     + "\n".join(f"- {t['term']}: {t['message']}" for t in failed_terms))
    parts.append("Explain the most likely cause and how to fix it without breaking what already passes.")
    return "\n\n".join(parts)


def parse(text: str) -> CriticOutput | None:
    """Validated output, or None if the reply does not match the schema (it is then stored raw only)."""
    match = _OBJECT.search(text or "")
    if not match:
        return None
    try:
        return CriticOutput.model_validate(json.loads(match.group(0)))
    except (ValueError, ValidationError):
        return None


def critique(llm: LLMClient, model: str, user_prompt: str) -> tuple[LLMResponse, CriticOutput | None, str]:
    response = llm.complete(model=model, system=SYSTEM, user=user_prompt)
    return response, parse(response.text), prompt_hash(model, SYSTEM, user_prompt)
