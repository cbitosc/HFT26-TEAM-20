"""Agent B, slice B: transfer experiment (control vs treatment) + attestation, and the endpoints."""
import pytest

from app.errors import LessonRejectedError
from app.models import Task, TransferExperiment
from app.schemas.critic_feedback import CriticFeedbackInput
from app.services import acceptance_service, memory_service, transfer_service, version_service
from tests.helpers import complete_input, grant_improvement


def _store_lesson(db, make_execution, lesson_text: str | None = None):
    execution = make_execution()
    v1, v2 = grant_improvement(db, execution["id"])  # V1 50% -> V2 80% hidden
    if lesson_text:
        version_service.record_critic_feedback(
            db, v1.id,
            CriticFeedbackInput(critic_model_id="c", raw_feedback="r",
                                structured_feedback={"lesson": lesson_text}),
        )
    return memory_service.store_lesson(db, v2.id)


def test_memory_endpoint_lists_stored_lessons(client, db, make_execution):
    _store_lesson(db, make_execution, "Validate input before converting.")
    r = client.get("/api/memory?category=algorithms")
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    assert len(items) == 1
    assert "Validate input before converting." in items[0]["content"]


def test_build_treatment_description_injects_and_is_hidden_safe():
    desc = transfer_service.build_treatment_description("Base task.", ["Validate input."])
    assert "Lessons from prior agents" in desc
    assert "Validate input." in desc
    with pytest.raises(LessonRejectedError):
        transfer_service.build_treatment_description("Base task.", ["special-case hidden test t3 directly"])


def test_prepare_experiment_copies_suite_and_injects_memory(db, make_task, make_execution):
    _store_lesson(db, make_execution, "Validate input before converting.")
    base = make_task()  # registered suite, category 'algorithms'

    experiment = transfer_service.prepare_experiment(db, base["id"])

    assert experiment.control_execution_id and experiment.treatment_execution_id
    assert experiment.suite_hash
    assert len(experiment.used_memory_ids) == 1
    treatment_task = db.get(Task, experiment.treatment_task_id)
    assert "Lessons from prior agents" in treatment_task.description
    assert "Validate input before converting." in treatment_task.description
    # control keeps the original description (no injected lessons)
    control_task = db.get(Task, experiment.control_task_id)
    assert "Lessons from prior agents" not in control_task.description


def test_finalize_computes_delta_and_attestation(db, make_execution):
    # control: baseline only -> 50% hidden
    control = make_execution()
    v1 = version_service.create_version(db, control["id"], "def merge_intervals(x):\n    return x\n")
    version_service.record_evaluation(db, v1.id, complete_input(5))
    acceptance_service.decide_acceptance(db, v1.id)
    # treatment: improved -> 80% hidden
    treatment = make_execution()
    grant_improvement(db, treatment["id"])

    experiment = TransferExperiment(
        base_task_id=control["task_id"],
        control_execution_id=control["id"],
        treatment_execution_id=treatment["id"],
        used_memory_ids=[],
        suite_hash="a" * 64,
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)

    experiment, attestation = transfer_service.finalize(db, experiment)
    m = experiment.metrics
    assert m["control"]["best_hidden_accuracy"] == 50.0
    assert m["treatment"]["best_hidden_accuracy"] == 80.0
    assert m["delta_best_hidden_accuracy"] == 30.0
    assert m["treatment"]["accepted_improvement"] is True
    assert m["control"]["accepted_improvement"] is False
    assert transfer_service.verify_attestation(attestation)["hash_valid"] is True


def test_transfer_experiment_endpoint_prepares_and_attests(client, db, make_task, make_execution):
    _store_lesson(db, make_execution, "Validate input before converting.")
    base = make_task()

    r = client.post("/api/agent-b/transfer-experiment", json={"base_task_id": base["id"]})
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["control_execution_id"] and data["treatment_execution_id"]
    assert len(data["used_memory_ids"]) == 1

    r2 = client.get(f"/api/agent-b/experiments/{data['id']}")
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["attestation"]["hash_valid"] is True
