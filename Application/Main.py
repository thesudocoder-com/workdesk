from __future__ import annotations

import os

from litestar import Litestar, Request, get
from litestar.exceptions import NotAuthorizedException, NotFoundException, PermissionDeniedException
from litestar.response import Response
from litestar.response import Redirect, Template
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig
from litestar.plugins.jinja import JinjaTemplateEngine

from Application.Authentication.Controller import AuthenticationController
from Application.Authentication.AccountController import AccountController
from Application.Authentication.Setup import owner_exists
from Application.Authentication.SetupController import SetupController
from Application.Authentication.Security import get_csrf_token, session_auth
from Application.Configurations import BASE_DIR, settings
from Application.Dashboard.Controller import DashboardController
from Application.Calendar.Controller import CalendarController
from Application.Clients.Controller import ClientsController
from Application.Engagements.Controller import EngagementsController
from Application.Projects.Controller import ProjectsController
from Application.Tasks.Controller import TasksController
from Application.Finance.Controller import FinanceController
from Application.Reports.Controller import ReportsController
from Application.Search.Controller import SearchController
from Application.Settings.Controller import SettingsController
from Application.Common.Money import format_cad, format_currency
from Application.Common.Time import to_toronto
from Application.Users.Controller import UsersController
from Application.Users.Repository import initialize_database


@get("/")
async def index(request: Request) -> Redirect:
    if not owner_exists():
        return Redirect("/Setup")
    return Redirect("/Dashboard" if request.scope.get("user") else "/Login")


@get("/health", exclude_from_auth=True)
async def health() -> dict[str, str]:
    return {"status": "ok"}


def handle_unauthorized(request: Request, exc: NotAuthorizedException) -> Redirect:
    if isinstance(request.session, dict) and request.session.pop("password_change_required", False):
        return Redirect("/Account/Password", status_code=303)
    return Redirect("/Setup" if not owner_exists() else "/Login", status_code=303)


def handle_forbidden(request: Request, exc: PermissionDeniedException) -> Template:
    return Template(
        "Errors/403.html",
        context={
            "page_title": "Access restricted",
            "page_eyebrow": "403 · Permission required",
            "current_section": "",
            "current_user": request.user,
            "csrf_token": get_csrf_token(request.session),
        },
        status_code=403,
    )


def handle_not_found(request: Request, exc: NotFoundException) -> Template | Redirect:
    if not request.user:
        return Redirect("/Login", status_code=303)
    return Template("Errors/404.html", context={"page_title":"Not found","page_eyebrow":"404","current_section":"","current_user":request.user,"csrf_token":get_csrf_token(request.session)}, status_code=404)


def add_security_headers(response: Response) -> Response:
    response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"strict-origin-when-cross-origin","Permissions-Policy":"camera=(), microphone=(), geolocation=()"})
    if settings.session_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def on_startup() -> None:
    if not settings.is_development:
        insecure_markers = {"dev-only-change-this-workdesk-secret", "local-development-only-change-before-deployment", "replace-with-a-long-random-secret"}
        required = ["WORKDESK_DATABASE_URL", "WORKDESK_SESSION_SECRET", "WORKDESK_SETUP_TOKEN", "WORKDESK_PUBLIC_URL", "WORKDESK_SESSION_SECURE"]
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing required production settings: {', '.join(missing)}")
        if len(settings.session_secret) < 32 or settings.session_secret in insecure_markers or settings.session_secret.startswith("replace-"):
            raise RuntimeError("Set WORKDESK_SESSION_SECRET to a unique value of at least 32 characters.")
        if not settings.session_secure:
            raise RuntimeError("WORKDESK_SESSION_SECURE must be true outside development.")
        if not settings.public_url.startswith("https://"):
            raise RuntimeError("WORKDESK_PUBLIC_URL must use HTTPS outside development.")
        if len(settings.setup_token) < 24 or settings.setup_token == "development-setup-token" or settings.setup_token.startswith("replace-"):
            raise RuntimeError("Set WORKDESK_SETUP_TOKEN to a unique value of at least 24 characters.")
    initialize_database()


def enforce_first_run_and_password(connection, route_handler) -> None:
    path = connection.url.path
    public = path in {"/", "/Login", "/Setup", "/health"} or path.startswith("/Static/")
    if not public and not owner_exists():
        raise NotAuthorizedException()
    user = connection.scope.get("user")
    if user and user.must_change_password and path not in {"/Account/Password", "/Logout"}:
        connection.session["password_change_required"] = True
        raise NotAuthorizedException()


def configure_templates(engine: JinjaTemplateEngine) -> None:
    engine.engine.globals.update(
        public_url=settings.public_url,
        social_image_url=f"{settings.public_url}/Static/Images/og.png",
        business_name="WorkDesk",
    )
    engine.engine.filters["cad"] = format_cad
    engine.engine.filters["money"] = format_currency
    engine.engine.filters["toronto"] = lambda value: to_toronto(value).strftime("%b %d, %Y · %I:%M %p")


app = Litestar(
    route_handlers=[
        index,
        health,
        SetupController,
        AuthenticationController,
        AccountController,
        DashboardController,
        CalendarController,
        ClientsController,
        EngagementsController,
        ProjectsController,
        TasksController,
        FinanceController,
        ReportsController,
        SearchController,
        SettingsController,
        UsersController,
        create_static_files_router(path="/Static", directories=[BASE_DIR / "Static"]),
    ],
    middleware=[session_auth.middleware],
    guards=[enforce_first_run_and_password],
    template_config=TemplateConfig(
        directory=BASE_DIR / "Templates",
        engine=JinjaTemplateEngine,
        engine_callback=configure_templates,
    ),
    exception_handlers={
        NotAuthorizedException: handle_unauthorized,
        PermissionDeniedException: handle_forbidden,
        NotFoundException: handle_not_found,
    },
    on_startup=[on_startup],
    after_request=add_security_headers,
    debug=settings.is_development,
)
