from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .Models import Client


class ClientRepository:
    def list(self, session: Session, query: str = "", status: str = "") -> list[Client]:
        statement = select(Client).options(selectinload(Client.engagements)).order_by(Client.name)
        if query:
            term = f"%{query.lower().strip()}%"
            statement = statement.where(
                or_(func.lower(Client.name).like(term), func.lower(Client.company_name).like(term))
            )
        if status:
            statement = statement.where(Client.status == status)
        return list(session.scalars(statement))

    def get(self, session: Session, client_id: int) -> Client | None:
        return session.scalar(
            select(Client)
            .where(Client.id == client_id)
            .options(selectinload(Client.engagements))
        )
