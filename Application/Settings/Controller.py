from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template
from pydantic import ValidationError

from Application.Authentication.Guards import developer_only
from Application.Authentication.Security import valid_csrf_token
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import page_context
from .Schemas import WorkspaceUpdate
from .Service import get_workspace, update_workspace


class SettingsController(Controller):
    path = "/Settings"
    guards = [developer_only]

    @get()
    async def index(self, request: Request) -> Template:
        return self._render(request)

    @post()
    async def update(self, request: Request) -> Template | Redirect:
        form = await request.form()
        errors: dict[str, str] = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            errors["form"] = "This form expired. Refresh and try again."
        try:
            data = WorkspaceUpdate.model_validate(clean_form(form))
        except ValidationError as exc:
            errors.update(form_errors(exc))
            data = None
        if data and not errors:
            update_workspace(data)
            request.session["flash"] = "Workspace settings saved."
            return Redirect("/Settings", status_code=303)
        return self._render(request, values=dict(form), errors=errors, status_code=422)

    @staticmethod
    def _render(request: Request, values=None, errors=None, status_code=200) -> Template:
        workspace = get_workspace()
        if workspace and values is None:
            values = {column.name: getattr(workspace, column.name) for column in workspace.__table__.columns}
        return Template("Settings/Index.html", context={
            **page_context(request, "Settings", "settings", "Workspace configuration"),
            "values": values or {},
            "errors": errors or {},
        }, status_code=status_code)
