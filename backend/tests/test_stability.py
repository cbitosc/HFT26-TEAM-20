"""Milestone 07B.1: the stale-evaluator-directory sweep and the no-leak guarantees.

The sweep exists because a hard-killed process (for example the CI harness killing a wedged run) cannot
run its own `finally` cleanup. A normal evaluation always removes its own directory."""
import time
from pathlib import Path

from app.evaluation.execution import EVAL_DIR_PREFIX, live_eval_children, sweep_stale_eval_dirs


def _make_dir(root: Path, name: str, age_seconds: float) -> Path:
    d = root / name
    d.mkdir()
    (d / "suite.json").write_text("decrypted hidden tests would live here")
    past = time.time() - age_seconds
    import os

    os.utime(d, (past, past))
    return d


def test_sweep_removes_old_evaluator_dirs_but_keeps_fresh_ones(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    old = _make_dir(tmp_path, f"{EVAL_DIR_PREFIX}old", age_seconds=7200)
    fresh = _make_dir(tmp_path, f"{EVAL_DIR_PREFIX}fresh", age_seconds=10)
    removed = sweep_stale_eval_dirs(max_age_seconds=3600)
    assert removed == 1
    assert not old.exists() and fresh.exists()


def test_sweep_never_touches_anything_without_the_prefix(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    # Old directories and files that are NOT ours must survive, even in the same temp root.
    other_dir = _make_dir(tmp_path, "someone_elses_data", age_seconds=99999)
    looks_close = _make_dir(tmp_path, "autoevolve_", age_seconds=99999)  # prefix is autoevolve_eval_, not this
    other_file = tmp_path / "important.txt"
    other_file.write_text("keep me")
    import os

    os.utime(other_file, (time.time() - 99999, time.time() - 99999))
    removed = sweep_stale_eval_dirs(max_age_seconds=1)
    assert removed == 0
    assert other_dir.exists() and looks_close.exists() and other_file.exists()


def test_sweep_tolerates_a_missing_temp_root(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "does-not-exist"))
    assert sweep_stale_eval_dirs(max_age_seconds=1) == 0


def test_a_normal_evaluation_leaves_no_child_and_no_directory(db, make_task):
    """Covered more broadly by the autouse teardown fixture; asserted directly here too."""
    import tempfile

    from app.services import evaluation_service as evs
    from app.services import execution_service as exe
    from app.services import version_service as ver

    before = {p.name for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith(EVAL_DIR_PREFIX)}
    eid = exe.create_execution(db, make_task()["id"]).id
    v1 = ver.create_version(db, eid, "def merge_intervals(x):\n    return list(x)\n")
    # a settings object with code execution allowed (the test settings are app_env='test')
    from app.config import Settings

    evs.evaluate_version(db, v1.id, Settings(_env_file=None, app_env="test", database_url="sqlite:///:memory:"))
    after = {p.name for p in Path(tempfile.gettempdir()).iterdir() if p.name.startswith(EVAL_DIR_PREFIX)}
    assert after == before  # the run removed its own working directory
    assert live_eval_children() == set()
