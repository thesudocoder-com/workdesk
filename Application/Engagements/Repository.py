from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from Application.Finance.Models import Invoice
from .Models import Engagement


class EngagementRepository:
    def list(self, session: Session, query: str = "", status: str = "") -> list[Engagement]:
        statement = select(Engagement).options(selectinload(Engagement.client), selectinload(Engagement.owner)).order_by(Engagement.created_at.desc())
        if query:
            statement = statement.where(func.lower(Engagement.name).like(f"%{query.lower().strip()}%"))
        if status:
            statement = statement.where(Engagement.status == status)
        return list(session.scalars(statement))

    def get(self, session: Session, engagement_id: int) -> Engagement | None:
        return session.scalar(select(Engagement).where(Engagement.id == engagement_id).options(selectinload(Engagement.client), selectinload(Engagement.owner), selectinload(Engagement.projects), selectinload(Engagement.milestones), selectinload(Engagement.invoices).selectinload(Invoice.payments)))
