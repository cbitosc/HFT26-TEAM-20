"""Agent B, slice A: cross-agent memory (store a lesson from an accepted improvement; retrieve;
refuse anything that would leak hidden test data)."""
import pytest

from app.errors import LessonRejectedError
from app.schemas.critic_feedback import CriticFeedbackInput
from app.services import memory_service, version_service
from tests.helpers import grant_improvement


def _improvement(db, make_execution):
    execution = make_execution()
    v1, v2 = grant_improvement(db, execution["id"])  # V1 50% -> V2 80% hidden, V2 accepted
    return execution, v1, v2


def test_store_lesson_from_validated_improvement(db, make_execution):
    execution, _v1, v2 = _improvement(db, make_execution)

    memory = memory_service.store_lesson(db, v2.id)

    assert memory is not None
    assert memory.task_category == "algorithms"
    assert memory.source_execution_id == execution["id"]
    assert "Lesson:" in memory.content
    # the measured, hidden-safe before -> after accuracy is recorded
    assert "50%" in memory.content and "80%" in memory.content


def test_store_lesson_prefers_the_critic_insight(db, make_execution):
    _execution, v1, v2 = _improvement(db, make_execution)
    version_service.record_critic_feedback(
        db,
        v1.id,
        CriticFeedbackInput(
            critic_model_id="critic-x",
            raw_feedback="full reply",
            structured_feedback={"diagnosis": "d", "suggestion": "s", "lesson": "Validate input before converting."},
        ),
    )

    memory = memory_service.store_lesson(db, v2.id)
    assert memory is not None
    assert "Validate input before converting." in memory.content


def test_no_memory_for_a_non_improvement(db, make_execution):
    _execution, v1, _v2 = _improvement(db, make_execution)
    # V1 is the baseline: it has no validated_improvement evidence, so nothing is learned.
    assert memory_service.store_lesson(db, v1.id) is None


def test_retrieve_filters_by_category_and_excludes_own_run(db, make_execution):
    execution, _v1, v2 = _improvement(db, make_execution)
    memory_service.store_lesson(db, v2.id)

    assert len(memory_service.retrieve(db, task_category="algorithms")) == 1
    assert memory_service.retrieve(db, task_category="nonexistent") == []
    assert memory_service.retrieve(db, task_category="algorithms",
                                   exclude_execution_id=execution["id"]) == []


def test_lesson_that_leaks_a_hidden_id_is_refused(db, make_execution):
    _execution, v1, v2 = _improvement(db, make_execution)
    # A Critic lesson that names a hidden test id (t3). The gate must refuse it.
    version_service.record_critic_feedback(
        db,
        v1.id,
        CriticFeedbackInput(
            critic_model_id="critic-x",
            raw_feedback="full reply",
            structured_feedback={"lesson": "To pass, special-case hidden test t3 directly."},
        ),
    )

    with pytest.raises(LessonRejectedError):
        memory_service.store_lesson(db, v2.id)

    # nothing was stored
    assert memory_service.retrieve(db, task_category="algorithms") == []
