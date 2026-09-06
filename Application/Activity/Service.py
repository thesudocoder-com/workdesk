from sqlalchemy.orm import Session

from .Models import Activity


class ActivityService:
    @staticmethod
    def record(
        session: Session,
        user_id: int,
        entity_type: str,
        entity_id: int,
        action: str,
        description: str,
        metadata: dict | None = None,
    ) -> Activity:
        event = Activity(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            description=description,
            activity_metadata=metadata,
        )
        session.add(event)
        return event
