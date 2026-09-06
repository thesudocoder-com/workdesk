from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template
from pydantic import ValidationError

from Application.Common.Forms import clean_form, form_errors
from Application.Configurations import settings
from .Security import get_csrf_token, valid_csrf_token
from .Setup import SetupError, SetupRequest, initialize_workspace, owner_exists


class SetupController(Controller):
    path = "/Setup"

    @get(exclude_from_auth=True)
    async def setup_page(self, request: Request) -> Template | Redirect:
        if owner_exists():
            return Redirect("/Login", status_code=303)
        return self._render(request)

    @post(exclude_from_auth=True)
    async def setup(self, request: Request) -> Template | Redirect:
        if owner_exists():
            return Redirect("/Login", status_code=303)
        form = await request.form()
        values = dict(form)
        errors: dict[str, str] = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            errors["form"] = "This setup form expired. Refresh and try again."
        try:
            data = SetupRequest.model_validate(clean_form(form))
        except ValidationError as exc:
            errors.update(form_errors(exc))
            data = None
        if not errors and data:
            try:
                owner = initialize_workspace(data)
            except SetupError as exc:
                errors["form"] = str(exc)
            else:
                request.session.clear()
                request.session.update({
                    "user_id": owner.id,
                    "session_version": owner.session_version,
                    "csrf_token": get_csrf_token({}),
                    "flash": "Your workspace is ready.",
                })
                return Redirect("/Dashboard", status_code=303)
        values.pop("password", None)
        values.pop("password_confirmation", None)
        values.pop("setup_token", None)
        return self._render(request, values=values, errors=errors, status_code=422 if errors else 400)

    @staticmethod
    def _render(request: Request, values=None, errors=None, status_code: int = 200) -> Template:
        return Template("Authentication/Setup.html", context={
            "app_name": settings.app_name,
            "csrf_token": get_csrf_token(request.session),
            "values": values or {},
            "errors": errors or {},
        }, status_code=status_code)
