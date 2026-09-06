from litestar import Request
from litestar.exceptions import PermissionDeniedException

from Application.Users.Models import UserRole


def developer_only(connection: Request, route_handler) -> None:
    if not connection.user or connection.user.role != UserRole.DEVELOPER.value:
        raise PermissionDeniedException("Developer access is required.")


def outreach_or_developer(connection: Request, route_handler) -> None:
    allowed = {UserRole.DEVELOPER.value, UserRole.OUTREACH_MANAGER.value}
    if not connection.user or connection.user.role not in allowed:
        raise PermissionDeniedException("Outreach Manager or Developer access is required.")
