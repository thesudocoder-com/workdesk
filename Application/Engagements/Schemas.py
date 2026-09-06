from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from Application.Common.Enums import BillingFrequency, EngagementStatus, EngagementType


class EngagementCreate(BaseModel):
    client_id: int
    name: str = Field(min_length=2, max_length=180)
    type: EngagementType
    description: str | None = Field(default=None, max_length=4000)
    contract_value: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = "CAD"
    billing_frequency: BillingFrequency = BillingFrequency.ONE_TIME
    start_date: date | None = None
    end_date: date | None = None
    owner_id: int
    status: EngagementStatus = EngagementStatus.ACTIVE

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be after the start date.")
        return self
