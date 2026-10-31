"""Provenance of an evaluation (PRD FR-3): what was run, with which configuration, where.

`evaluator_config` is everything that can change a measured outcome: the evaluator version, the time
limits (a timeout is a failure), the interpreter version and flags, and the source of the evaluator
modules themselves. Its hash is committed when an execution starts; an evaluation made under a
different configuration cannot be compared with one made under the committed one.

The environment description is informational. There is no container yet, so there is no runner
image digest (it is recorded as null, not invented).
"""
import hashlib
import json
import platform
import sys
from pathlib import Path

from app.evaluation.execution import RunLimits
from app.evaluation.suite import EVALUATOR_VERSION

_PACKAGE = Path(__file__).parent
EVALUATOR_SOURCES = ("_runner.py", "execution.py", "engine.py", "static_quality.py", "suite.py")
RUNNER_FLAGS = ("-s", "-B")


def _source_digests() -> dict[str, str]:
    return {name: hashlib.sha256((_PACKAGE / name).read_bytes()).hexdigest() for name in EVALUATOR_SOURCES}


def evaluator_config(limits: RunLimits) -> dict:
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "per_run_timeout_seconds": float(limits.per_run_timeout),
        "total_timeout_seconds": float(limits.total_timeout),
        "interpreter": f"{platform.python_implementation()} {platform.python_version()}",
        "runner_flags": list(RUNNER_FLAGS),
        "hash_seed": "0",
        "source_sha256": _source_digests(),
    }


def config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluator_config_hash(limits: RunLimits) -> str:
    return config_hash(evaluator_config(limits))


def environment() -> dict:
    return {
        "os": platform.system(),
        "platform": platform.platform(terse=True),
        "python": sys.version.split()[0],
        "isolation": "subprocess with time limits; NOT a security sandbox",
        "runner_image_digest": None,  # no containerized runner exists yet
    }
