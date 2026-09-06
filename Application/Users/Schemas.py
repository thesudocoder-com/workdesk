from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from .Models import UserRole


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: UserRole = UserRole.TEAM_MEMBER
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        return self


class UserRoleUpdate(BaseModel):
    role: UserRole


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        return self
