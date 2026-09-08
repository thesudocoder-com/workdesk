from pydantic import BaseModel, EmailStr, Field, field_validator

from Application.Common.Enums import ClientStatus


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    company_name: str | None = Field(default=None, max_length=180)
    legal_name: str | None = Field(default=None, max_length=180)
    default_currency: str = Field(default="CAD", min_length=3, max_length=3)
    tax_identifiers: str | None = Field(default=None, max_length=1000)
    primary_email: EmailStr | None = None
    primary_phone: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=255)
    status: ClientStatus = ClientStatus.ACTIVE
    address_line1: str | None = Field(default=None, max_length=180)
    address_line2: str | None = Field(default=None, max_length=180)
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=80)
    postal_code: str | None = Field(default=None, max_length=16)
    country: str = Field(default="Canada", max_length=80)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name", "company_name")
    @classmethod
    def clean_names(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value


class ClientUpdate(ClientCreate):
    pass
