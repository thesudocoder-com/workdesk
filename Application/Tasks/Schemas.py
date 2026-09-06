from datetime import date

from pydantic import BaseModel, Field

from Application.Common.Enums import Priority, TaskStatus


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(min_length=2, max_length=220)
    description: str | None = Field(default=None, max_length=4000)
    assigned_to_id: int | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
