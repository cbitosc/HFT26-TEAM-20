from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models import Task
from app.schemas.task import TaskCreate


def commit_or_rollback(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def create_task(session: Session, data: TaskCreate) -> Task:
    task = Task(
        title=data.title,
        description=data.description,
        requirements=list(data.requirements),
        language=data.language,
        category=data.category,
        evaluation_suite_id=data.evaluation_suite_id,
        starter_code=data.starter_code or None,
    )
    session.add(task)
    commit_or_rollback(session)
    return task


def get_task(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError("task", task_id)
    return task


def list_tasks(session: Session, *, limit: int, offset: int) -> tuple[list[Task], int]:
    total = session.scalar(select(func.count()).select_from(Task)) or 0
    items = session.scalars(
        select(Task).order_by(Task.created_at.desc(), Task.id).limit(limit).offset(offset)
    ).all()
    return list(items), total
