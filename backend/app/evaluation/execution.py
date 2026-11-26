"""Run candidate code in a child interpreter and collect per-item outcomes.

THIS IS NOT A SECURITY SANDBOX (see _runner.py and docs/EVALUATION_ENGINE.md). What it does provide:
  * a fresh interpreter per run (the real interpreter, not the venv launcher, so kill() really kills)
  * a strict wall-clock limit per run and for the whole evaluation
  * closed stdin; the candidate's own stdout/stderr discarded; our diagnostics read with a hard cap
  * a throwaway working directory with TEMP/TMP pointed into it, removed afterwards
  * a minimal, fixed environment (PYTHONHASHSEED=0 so results are reproducible)
  * isolation between items: every test starts from a freshly executed module
If one test hangs or crashes the process, that test fails and the remaining tests run in a new process.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.evaluation.suite import EvaluationSuite

RUNNER_SOURCE = Path(__file__).with_name("_runner.py")
SMOKE_ID = "__contract_smoke__"
EVAL_DIR_PREFIX = "autoevolve_eval_"  # every evaluator working directory starts with this
MAX_SOURCE_BYTES = 200_000
MAX_RESULT_BYTES = 2_000_000
MAX_DIAGNOSTIC_BYTES = 4_000
CLIP = 300


@dataclass(frozen=True)
class RunLimits:
    per_run_timeout: float = 10.0  # one interpreter run
    total_timeout: float = 60.0  # the whole evaluation, including restarts


@dataclass
class ItemOutcome:
    id: str
    passed: bool
    expected: str | None = None
    actual: str | None = None
    exception: str | None = None
    trace: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    imports_cleanly: bool = False
    entrypoint_defined: bool = False
    arity_ok: bool = False
    error: str | None = None
    trace: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    compiles: bool
    compile_error: str | None
    import_info: ImportInfo
    outcomes: dict[str, ItemOutcome]  # test ids and SMOKE_ID
    processes_started: int = 0
    timed_out_items: list[str] = field(default_factory=list)
    diagnostics: str = ""  # bounded stderr excerpt, for logs only; never scored


def _clip(text: str, limit: int = CLIP) -> str:
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _child_environment(workdir: str) -> dict[str, str]:
    env = {
        "PYTHONHASHSEED": "0",  # reproducible hashing/ordering
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "TEMP": workdir,
        "TMP": workdir,
        "TMPDIR": workdir,
    }
    for name in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR"):  # Windows needs these to start Python
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _interpreter() -> str:
    # In a venv on Windows, sys.executable is a launcher that spawns the real interpreter as a
    # child; killing the launcher would orphan the real process. The base interpreter is one process.
    return getattr(sys, "_base_executable", None) or sys.executable


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = path.read_bytes()[:MAX_RESULT_BYTES].decode("utf-8", errors="replace")
    records = []
    for line in data.splitlines():
        if len(line) > 20_000:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue  # malformed lines are ignored, never trusted
        if isinstance(record, dict) and record.get("t") in {"start", "import", "result", "done"}:
            records.append(record)
    return records


_LIVE_CHILDREN: set[int] = set()  # pids of evaluator child processes currently running (observability only)


def live_eval_children() -> set[int]:
    """Pids of evaluator children still running. Always empty between runs: every child is waited on
    (or killed then waited on) before `run_candidate` returns. Tests assert this after each test."""
    return set(_LIVE_CHILDREN)


def _spawn(workdir: Path, timeout: float) -> tuple[bool, int | None]:
    with open(workdir / "child_stdout.txt", "wb") as out, open(workdir / "child_stderr.txt", "wb") as err:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [_interpreter(), "-s", "-B", "runner_main.py"],
            cwd=workdir, env=_child_environment(str(workdir)), stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, creationflags=flags,
        )
        _LIVE_CHILDREN.add(process.pid)  # recorded only; the kill/wait logic below is unchanged
        try:
            try:
                process.wait(timeout=timeout)
                return False, process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return True, None
        finally:
            _LIVE_CHILDREN.discard(process.pid)


def _item_specs(suite: EvaluationSuite) -> list[dict]:
    smoke = {"id": SMOKE_ID, "checks": [{"kind": "returns_type", "args": repr(suite.contract.smoke_args),
                                         "expected": suite.contract.smoke_type}]}
    tests = [{"id": t.id, "checks": [{"kind": c.kind, "args": repr(c.args), "expected": c.expected
                                      if c.kind in {"raises", "all_items_of_type"} else repr(c.expected)}
                                     for c in t.checks]} for t in suite.tests]
    return [smoke, *tests]


def _failed(item_id: str, reason: str, exception: str | None = None) -> ItemOutcome:
    return ItemOutcome(item_id, False, expected="the item to run to completion", actual=reason, exception=exception)


def sweep_stale_eval_dirs(max_age_seconds: float = 3600.0) -> int:
    """Delete evaluator working directories left behind by a process that was hard-killed before its
    `finally` cleanup could run (a normal run always removes its own directory). Returns the count removed.

    Safety: it only considers entries DIRECTLY under the system temp directory whose name starts with
    EVAL_DIR_PREFIX and which are real directories (not symlinks), older than `max_age_seconds`. It never
    recurses into, or deletes, anything whose name does not carry the prefix, so it cannot touch unrelated
    files even if they sit in the same temp directory."""
    if not EVAL_DIR_PREFIX:  # defensive: an empty prefix would match everything
        return 0
    root = Path(tempfile.gettempdir())
    now = time.time()
    removed = 0
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.name.startswith(EVAL_DIR_PREFIX):
            continue
        try:
            if entry.is_symlink() or not entry.is_dir():
                continue
            if now - entry.stat().st_mtime < max_age_seconds:
                continue
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        except OSError:
            continue
    return removed


def run_candidate(source: str, suite: EvaluationSuite, limits: RunLimits) -> RunReport:
    items = _item_specs(suite)
    ids = [item["id"] for item in items]

    def all_failed(reason: str, import_info: ImportInfo, compiles: bool = True, error: str | None = None) -> RunReport:
        return RunReport(compiles, error, import_info, {i: _failed(i, reason) for i in ids})

    if len(source.encode("utf-8", errors="replace")) > MAX_SOURCE_BYTES:
        return all_failed(f"source larger than {MAX_SOURCE_BYTES} bytes was not executed", ImportInfo(), True)
    try:
        compile(source, "candidate.py", "exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError) as exc:
        message = _clip(f"{type(exc).__name__}: {exc}")
        return all_failed("source does not compile", ImportInfo(error=message), compiles=False, error=message)

    workdir = Path(tempfile.mkdtemp(prefix=EVAL_DIR_PREFIX))
    deadline = time.monotonic() + limits.total_timeout
    outcomes: dict[str, ItemOutcome] = {}
    import_info: ImportInfo | None = None
    timed_out: list[str] = []
    processes = 0
    diagnostics = ""
    try:
        (workdir / "candidate.py").write_text(source, encoding="utf-8")
        shutil.copyfile(RUNNER_SOURCE, workdir / "runner_main.py")
        pending = list(ids)
        for _ in range(len(ids) + 2):  # every iteration resolves at least one item, so this terminates
            remaining = deadline - time.monotonic()
            if not pending or remaining <= 0:
                break
            result_file = workdir / f"results_{processes}.jsonl"
            spec = {"entrypoint": suite.entrypoint, "arity": suite.contract.arity,
                    "result_file": result_file.name, "items": [i for i in items if i["id"] in pending]}
            (workdir / "suite.json").write_text(json.dumps(spec), encoding="utf-8")
            processes += 1
            hung, code = _spawn(workdir, min(limits.per_run_timeout, remaining))
            records = _read_records(result_file)

            started = None
            finished = False
            for record in records:
                kind = record["t"]
                if kind == "start":
                    started = record.get("id")
                elif kind == "import" and import_info is None:
                    import_info = ImportInfo(
                        imports_cleanly=bool(record.get("imports_cleanly")),
                        entrypoint_defined=bool(record.get("entrypoint_defined")),
                        arity_ok=bool(record.get("arity_ok")),
                        error=_clip(str(record["error"])) if record.get("error") else None,
                        trace=[_clip(str(t), 200) for t in record.get("trace", [])][:3],
                    )
                elif kind == "result" and record.get("id") in pending and isinstance(record.get("passed"), bool):
                    started = None
                    outcomes[record["id"]] = ItemOutcome(
                        record["id"], record["passed"],
                        _clip(str(record["expected"])) if record.get("expected") is not None else None,
                        _clip(str(record["actual"])) if record.get("actual") is not None else None,
                        _clip(str(record["exception"])) if record.get("exception") else None,
                        [_clip(str(t), 200) for t in record.get("trace", [])][:3],
                    )
                elif kind == "done":
                    finished = True

            stderr_file = workdir / "child_stderr.txt"
            if stderr_file.exists() and not diagnostics:
                diagnostics = stderr_file.read_bytes()[:MAX_DIAGNOSTIC_BYTES].decode("utf-8", errors="replace")

            if import_info is None:  # the module never finished importing: hang, crash or exit
                reason = (f"module import did not finish within {limits.per_run_timeout}s" if hung
                          else f"interpreter exited (code {code}) while importing the module")
                import_info = ImportInfo(error=reason)
                if hung:
                    timed_out.append("__import__")
                for item_id in pending:
                    outcomes[item_id] = _failed(item_id, reason, "Timeout" if hung else f"ExitCode {code}")
                pending = []
                break
            if not (import_info.imports_cleanly and import_info.entrypoint_defined):
                why = import_info.error or "the required entry point is not defined"
                for item_id in pending:
                    outcomes[item_id] = _failed(item_id, f"not run: {why}")
                pending = []
                break

            pending = [i for i in pending if i not in outcomes]
            if started in pending:  # the item that was running when the process stopped
                if hung:
                    timed_out.append(started)
                    outcomes[started] = _failed(started, f"timed out after {limits.per_run_timeout}s", "Timeout")
                elif not finished:
                    outcomes[started] = _failed(started, f"interpreter exited (code {code}) during this item",
                                                f"ExitCode {code}")
                pending = [i for i in pending if i not in outcomes]
            elif pending and not finished:  # stopped between items or without progress: stop retrying
                for item_id in pending:
                    outcomes[item_id] = _failed(item_id, "interpreter stopped before this item ran")
                pending = []
        for item_id in pending:  # budget exhausted
            outcomes[item_id] = _failed(item_id, f"not run: evaluation time budget of {limits.total_timeout}s was used up")
    finally:
        for attempt in range(5):  # Windows may hold a handle for a moment after a kill
            try:
                shutil.rmtree(workdir)
                break
            except OSError:
                time.sleep(0.1 * (attempt + 1))
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    return RunReport(True, None, import_info or ImportInfo(), outcomes, processes, timed_out, diagnostics)
