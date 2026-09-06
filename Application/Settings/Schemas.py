from pydantic import BaseModel, EmailStr, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class WorkspaceUpdate(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    legal_name: str = Field(default="", max_length=160)
    business_email: EmailStr | None = None
    business_phone: str = Field(default="", max_length=60)
    address_line1: str = Field(default="", max_length=240)
    city: str = Field(default="", max_length=120)
    region: str = Field(default="", max_length=120)
    postal_code: str = Field(default="", max_length=30)
    country: str = Field(default="", max_length=80)
    timezone: str = Field(default="UTC", max_length=80)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    invoice_prefix: str = Field(default="WD-", min_length=1, max_length=20)
    payment_terms_days: int = Field(default=15, ge=0, le=365)
    tax_information: str = Field(default="", max_length=2000)
    invoice_footer: str = Field(default="", max_length=2000)

    @field_validator("business_name", "legal_name", "business_phone", "address_line1", "city", "region", "postal_code", "country", "invoice_prefix")
    @classmethod
    def normalize(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("currency")
    @classmethod
    def currency_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("Enter a three-letter currency code.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Enter a valid IANA timezone, such as Asia/Kolkata.") from exc
        return value
