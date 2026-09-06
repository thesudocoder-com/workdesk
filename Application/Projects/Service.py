from Application.Activity.Service import ActivityService
from Application.Common.Enums import ProjectStatus
from Application.Common.Time import now_utc
from Application.Users.Repository import session_scope
from .Models import Project
from .Repository import ProjectRepository
from .Schemas import ProjectCreate
from Application.Engagements.Models import Engagement
from Application.Common.Enums import EngagementStatus
from Application.Users.Models import User


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
