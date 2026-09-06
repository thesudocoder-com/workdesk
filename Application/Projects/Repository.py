from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from Application.Engagements.Models import Engagement
from Application.Tasks.Models import WorkTask
from .Models import Project


class ProjectRepository:
    def list(self, session: Session, query: str = "", status: str = "", owner_id: int | None = None) -> list[Project]:
        statement = select(Project).options(selectinload(Project.engagement).selectinload(Engagement.client), selectinload(Project.owner), selectinload(Project.tasks)).order_by(Project.due_date.is_(None), Project.due_date)
        if query:
            statement = statement.where(func.lower(Project.name).like(f"%{query.lower().strip()}%"))
        if status:
            statement = statement.where(Project.status == status)
        if owner_id:
            statement = statement.where(Project.owner_id == owner_id)
        return list(session.scalars(statement))

    def get(self, session: Session, project_id: int) -> Project | None:
        return session.scalar(select(Project).where(Project.id == project_id).options(selectinload(Project.engagement).selectinload(Engagement.client), selectinload(Project.owner), selectinload(Project.tasks).selectinload(WorkTask.assignee)))
