from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from Application.Projects.Models import Project
from .Models import WorkTask


class TaskRepository:
    def list(self, session: Session, query: str = "", status: str = "", assignee_id: int | None = None) -> list[WorkTask]:
        statement = select(WorkTask).options(selectinload(WorkTask.project).selectinload(Project.engagement), selectinload(WorkTask.assignee)).order_by(WorkTask.due_date.is_(None), WorkTask.due_date, WorkTask.sort_order)
        if query:
            statement = statement.where(func.lower(WorkTask.title).like(f"%{query.lower().strip()}%"))
        if status:
            statement = statement.where(WorkTask.status == status)
        if assignee_id:
            statement = statement.where(WorkTask.assigned_to_id == assignee_id)
        return list(session.scalars(statement))

    def get(self, session: Session, task_id: int) -> WorkTask | None:
        return session.get(WorkTask, task_id)
