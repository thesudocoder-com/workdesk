from Application.Activity.Service import ActivityService
from Application.Common.Enums import TaskStatus
from Application.Common.Time import now_utc
from Application.Projects.Models import Project
from Application.Common.Enums import ProjectStatus
from Application.Users.Models import User
from Application.Users.Repository import session_scope
from .Models import WorkTask
from .Repository import TaskRepository
from .Schemas import TaskCreate, TaskStatusUpdate


class TaskService:
    def __init__(self) -> None:
        self.repository = TaskRepository()

    def list(self, query: str = "", status: str = "", assignee_id: int | None = None) -> list[WorkTask]:
        with session_scope() as session:
            return self.repository.list(session, query, status, assignee_id)

    def create(self, data: TaskCreate, actor_id: int) -> WorkTask:
        with session_scope() as session:
            project = session.get(Project, data.project_id)
            if not project or project.status in {ProjectStatus.COMPLETED.value, ProjectStatus.CANCELLED.value}:
                raise ValueError("Select an open project.")
            if data.assigned_to_id:
                assignee = session.get(User, data.assigned_to_id)
                if not assignee or not assignee.is_active:
                    raise ValueError("Select an active assignee.")
            task = WorkTask(**data.model_dump(), created_by_id=actor_id)
            session.add(task)
            session.flush()
            ActivityService.record(session, actor_id, "Task", task.id, "created", f"created task {task.title}")
            self._update_project_progress(session, task.project_id)
            return task

    def update_status(self, task_id: int, data: TaskStatusUpdate, actor_id: int) -> WorkTask:
        with session_scope() as session:
            task = self.repository.get(session, task_id)
            if not task:
                raise ValueError("Task not found.")
            task.status = data.status.value
            task.completed_at = now_utc() if data.status == TaskStatus.DONE else None
            ActivityService.record(session, actor_id, "Task", task.id, "updated", f"marked {task.title} as {task.status}")
            session.flush()
            self._update_project_progress(session, task.project_id)
            return task

    @staticmethod
    def _update_project_progress(session, project_id: int) -> None:
        project = session.get(Project, project_id)
        if not project:
            return
        tasks = list(project.tasks)
        project.progress = round(sum(task.status == TaskStatus.DONE.value for task in tasks) / len(tasks) * 100) if tasks else 0
