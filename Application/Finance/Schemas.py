from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from Application.Common.Enums import (
    AgreementStatus, BillingFrequency, BillingTiming, ExpenseCategory, InvoiceStatus,
    MilestoneStatus, PaymentMethod, RecurringStatus,
)


class AgreementCreate(BaseModel):
    engagement_id: int
    name: str = Field(min_length=2, max_length=180)
    contract_value: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    adjustment_amount: Decimal = Field(default=Decimal("0.00"), max_digits=14, decimal_places=2)
    adjustment_reason: str | None = Field(default=None, max_length=240)
    status: AgreementStatus = AgreementStatus.ACTIVE


class InstalmentCreate(BaseModel):
    agreement_id: int
    name: str = Field(min_length=2, max_length=180)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date | None = None
    sequence: int = Field(default=0, ge=0)


class RecurringServiceCreate(BaseModel):
    engagement_id: int
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    frequency: BillingFrequency
    interval: int = Field(default=1, ge=1, le=120)
    start_date: date
    end_date: date | None = None
    status: RecurringStatus = RecurringStatus.ACTIVE
    tax_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    billing_timing: BillingTiming = BillingTiming.ADVANCE

    @model_validator(mode="after")
    def validate_recurrence(self):
        if self.frequency == BillingFrequency.ONE_TIME:
            raise ValueError("Recurring services require a recurring frequency.")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date.")
        return self


class RecurringServiceUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    end_date: date | None = None
    tax_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    billing_timing: BillingTiming = BillingTiming.ADVANCE


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
