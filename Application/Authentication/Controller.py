from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template

from Application.Configurations import settings
from .Schemas import LoginRequest
from .Security import get_csrf_token, valid_csrf_token
from .Service import AuthenticationError, AuthenticationService
from .Setup import owner_exists


_login_attempts: dict[str, deque[datetime]] = defaultdict(deque)


def _rate_limited(request: Request) -> bool:
    address = request.client.host if request.client else "unknown"
    now = datetime.now(UTC)
    attempts = _login_attempts[address]
    while attempts and attempts[0] < now - timedelta(minutes=5):
        attempts.popleft()
    if len(attempts) >= 8:
        return True
    attempts.append(now)
    return False


class AuthenticationController(Controller):
    path = "/"

    @get("Login", exclude_from_auth=True)
    async def login_page(self, request: Request) -> Template:
        if not owner_exists():
            return Redirect("/Setup", status_code=303)
        if request.scope.get("user"):
            return Redirect("/Dashboard")
        return self._render_login(request)

    @post("Login", exclude_from_auth=True)
    async def login(self, request: Request) -> Template | Redirect:
        if not owner_exists():
            return Redirect("/Setup", status_code=303)
        form = await request.form()
        if _rate_limited(request):
            return self._render_login(request, error="Too many sign-in attempts. Try again in five minutes.", email=str(form.get("email", "")), status_code=429)
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            return self._render_login(
                request,
                error="Your sign-in page expired. Please try again.",
                email=str(form.get("email", "")),
                status_code=400,
            )
        try:
            credentials = LoginRequest.model_validate(
                {"email": form.get("email"), "password": form.get("password")}
            )
            user = AuthenticationService().authenticate(credentials)
        except (ValidationError, AuthenticationError) as exc:
            message = "Enter a valid email address and password."
            if isinstance(exc, AuthenticationError):
                message = str(exc)
            return self._render_login(
                request,
                error=message,
                email=str(form.get("email", "")),
                status_code=422,
            )

        request.session.clear()
        if request.client:
            _login_attempts.pop(request.client.host, None)
        request.session.update({"user_id": user.id, "session_version": user.session_version, "csrf_token": get_csrf_token({})})
        request.session["flash"] = f"Welcome back, {user.name.split()[0]}."
        return Redirect("/Account/Password" if user.must_change_password else "/Dashboard", status_code=303)

    @post("Logout")
    async def logout(self, request: Request) -> Redirect:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            return Redirect("/Dashboard", status_code=303)
        request.session.clear()
        return Redirect("/Login", status_code=303)

    @staticmethod
    def _render_login(
        request: Request,
        *,
        error: str | None = None,
        email: str = "",
        status_code: int = 200,
    ) -> Template:
        return Template(
            "Authentication/Login.html",
            context={
                "app_name": settings.app_name,
                "csrf_token": get_csrf_token(request.session),
                "error": error,
                "email": email,
            },
            status_code=status_code,
        )
