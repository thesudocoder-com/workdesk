from datetime import date

from pydantic import BaseModel, Field, model_validator

from Application.Common.Enums import Priority, ProjectStatus


class ProjectCreate(BaseModel):
    engagement_id: int
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: int
    status: ProjectStatus = ProjectStatus.PLANNING
    priority: Priority = Priority.MEDIUM
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("Due date must be after the start date.")
        return self


class ProjectUpdate(BaseModel):
    engagement_id: int
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: int
    status: ProjectStatus = ProjectStatus.PLANNING
    priority: Priority = Priority.MEDIUM
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("Due date must be after the start date.")
        return self

