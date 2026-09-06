from Application.Users.Repository import session_scope
from .Queries import dashboard_data


class DashboardService:
    def get(self, user_id: int, include_finance: bool) -> dict:
        with session_scope() as session:
            return dashboard_data(session, user_id, include_finance)
