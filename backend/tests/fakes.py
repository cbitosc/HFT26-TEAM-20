"""A scripted LLM client for tests. Nothing here touches the network."""
from dataclasses import dataclass, field
from pathlib import Path

from app.agents import critic as critic_agent
from app.agents import generator as generator_agent
from app.llm.client import LLMResponse

FIXTURES = Path(__file__).parent / "fixtures"


def code_reply(name: str) -> str:
    """A Generator reply: one fenced block containing a fixture's source."""
    return "Here is the code:\n```python\n" + (FIXTURES / f"{name}.py").read_text(encoding="utf-8") + "```\n"


def critic_reply(diagnosis="The merge loop assumes sorted input.", suggestion="Sort a copy before merging.",
                 lesson="Never mutate the caller's list.") -> str:
    import json

    return json.dumps({"diagnosis": diagnosis, "suggestion": suggestion, "lesson": lesson})


@dataclass
class Call:
    role: str
    model: str
    system: str
    user: str


@dataclass
class FakeLLMClient:
    """`generator` and `critic` are queues of replies: a string, an Exception (raised), or a callable
    taking the Call and returning either. `on_call` runs before each reply (to cancel, inspect the
    session, and so on)."""

    generator: list = field(default_factory=list)
    critic: list = field(default_factory=list)
    on_call: object = None
    calls: list = field(default_factory=list)
    returned_model: str | None = "featherless/returned-model"

    def complete(self, *, model: str, system: str, user: str) -> LLMResponse:
        role = "generator" if system == generator_agent.SYSTEM else "critic" if system == critic_agent.SYSTEM else "?"
        call = Call(role, model, system, user)
        self.calls.append(call)
        if self.on_call:
            self.on_call(call)
        queue = self.generator if role == "generator" else self.critic
        if not queue:
            raise AssertionError(f"unexpected {role} call #{sum(c.role == role for c in self.calls)}")
        reply = queue.pop(0)
        if callable(reply) and not isinstance(reply, Exception):
            reply = reply(call)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(text=reply, requested_model=model, returned_model=self.returned_model,
                           latency_seconds=0.01, prompt_tokens=100, completion_tokens=50, total_tokens=150,
                           attempts=1)
