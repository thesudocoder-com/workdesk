from sqlalchemy import select

from Application.Activity.Service import ActivityService
from Application.Common.Enums import EngagementStatus, ProjectStatus
from Application.Common.Time import now_utc
from Application.Engagements.Models import Engagement
from Application.Finance.Models import Expense
from Application.Users.Models import User
from Application.Users.Repository import session_scope
from .Models import Project
from .Repository import ProjectRepository
from .Schemas import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self) -> None:
        self.repository = ProjectRepository()

    def list(self, query: str = "", status: str = "", owner_id: int | None = None) -> list[Project]:
        with session_scope() as session:
            return self.repository.list(session, query, status, owner_id)

    def get(self, project_id: int) -> Project | None:
        with session_scope() as session:
            return self.repository.get(session, project_id)

    def create(self, data: ProjectCreate, actor_id: int) -> Project:
        with session_scope() as session:
            if data.status in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}:
                raise ValueError("New projects must start in an open status.")
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement or engagement.status != EngagementStatus.ACTIVE.value:
                raise ValueError("Select an active engagement.")
            owner = session.get(User, data.owner_id)
            if not owner or not owner.is_active:
                raise ValueError("Select an active owner.")
            project = Project(**data.model_dump())
            session.add(project)
            session.flush()
            ActivityService.record(session, actor_id, "Project", project.id, "created", f"created project {project.name}")
            return project

    def update(self, project_id: int, data: ProjectUpdate, actor_id: int) -> Project:
        with session_scope() as session:
            project = self.repository.get(session, project_id)
            if not project:
                raise ValueError("Project not found.")
            engagement = session.get(Engagement, data.engagement_id)
            if not engagement or engagement.status != EngagementStatus.ACTIVE.value:
                raise ValueError("Select an active engagement.")
            owner = session.get(User, data.owner_id)
            if not owner or not owner.is_active:
                raise ValueError("Select an active owner.")
            for key, value in data.model_dump().items():
                setattr(project, key, value)
            if data.status == ProjectStatus.COMPLETED and not project.completed_at:
                project.completed_at = now_utc()
                project.progress = 100
            elif data.status != ProjectStatus.COMPLETED and project.completed_at:
                project.completed_at = None
                if project.tasks:
                    done_count = sum(1 for t in project.tasks if t.status == "Done")
                    project.progress = int((done_count / len(project.tasks)) * 100)
                else:
                    project.progress = 0
            ActivityService.record(session, actor_id, "Project", project.id, "updated", f"updated project {project.name}")
            return project

    def delete(self, project_id: int, actor_id: int) -> None:
        with session_scope() as session:
            project = self.repository.get(session, project_id)
            if not project:
                raise ValueError("Project not found.")
            name = project.name
            for task in list(project.tasks):
                session.delete(task)
            expenses = list(session.scalars(select(Expense).where(Expense.project_id == project_id)))
            for exp in expenses:
                session.delete(exp)
            session.delete(project)
            session.flush()
            ActivityService.record(session, actor_id, "Project", project_id, "deleted", f"deleted project {name}")

    def complete(self, project_id: int, actor_id: int) -> Project:
        with session_scope() as session:
            project = self.repository.get(session, project_id)
            if not project:
                raise ValueError("Project not found.")
            if not project.tasks:
                raise ValueError("Add and complete at least one task before completing this project.")
            if any(task.status != "Done" for task in project.tasks):
                raise ValueError("Every project task must be done before the project can be completed.")
            project.status = ProjectStatus.COMPLETED.value
            project.completed_at = now_utc()
            project.progress = 100
            ActivityService.record(
                session, actor_id, "Project", project.id, "completed", f"completed project {project.name}"
            )
            return project

