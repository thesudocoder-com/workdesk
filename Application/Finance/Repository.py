from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .Models import Expense, Invoice, Payment, PaymentMilestone


class FinanceRepository:
    def invoices(self, session: Session, status: str = "") -> list[Invoice]:
        statement = select(Invoice).options(selectinload(Invoice.client), selectinload(Invoice.engagement), selectinload(Invoice.payments)).order_by(Invoice.due_date.desc())
        if status:
            statement = statement.where(Invoice.status == status)
        return list(session.scalars(statement))

    def invoice(self, session: Session, invoice_id: int) -> Invoice | None:
        return session.scalar(select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.client), selectinload(Invoice.engagement), selectinload(Invoice.payments), selectinload(Invoice.milestone)))

    def milestones(self, session: Session, engagement_id: int | None = None) -> list[PaymentMilestone]:
        statement = select(PaymentMilestone).options(selectinload(PaymentMilestone.engagement)).order_by(PaymentMilestone.due_date)
        if engagement_id:
            statement = statement.where(PaymentMilestone.engagement_id == engagement_id)
        return list(session.scalars(statement))

    def payments(self, session: Session) -> list[Payment]:
        return list(session.scalars(select(Payment).options(selectinload(Payment.invoice).selectinload(Invoice.client)).order_by(Payment.paid_at.desc())))

    def expenses(self, session: Session) -> list[Expense]:
        return list(session.scalars(select(Expense).options(selectinload(Expense.project), selectinload(Expense.engagement)).order_by(Expense.expense_date.desc())))
