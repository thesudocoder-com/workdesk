from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from Application.Common.Enums import ExpenseCategory, InvoiceStatus, MilestoneStatus, PaymentMethod


class MilestoneCreate(BaseModel):
    engagement_id: int
    name: str = Field(min_length=2, max_length=180)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date | None = None
    status: MilestoneStatus = MilestoneStatus.UPCOMING


class InvoiceCreate(BaseModel):
    engagement_id: int
    payment_milestone_id: int | None = None
    issue_date: date
    due_date: date
    subtotal: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=14, decimal_places=2)
    status: InvoiceStatus = InvoiceStatus.SENT
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.due_date < self.issue_date:
            raise ValueError("Due date must be on or after the issue date.")
        return self


class PaymentCreate(BaseModel):
    invoice_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    paid_at: datetime
    payment_method: PaymentMethod
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class ExpenseCreate(BaseModel):
    engagement_id: int | None = None
    project_id: int | None = None
    category: ExpenseCategory
    vendor: str = Field(min_length=2, max_length=140)
    description: str = Field(min_length=2, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expense_date: date
