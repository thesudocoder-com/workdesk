from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template
from pydantic import BaseModel, Field, ValidationError, model_validator

from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import page_context
from Application.Users.Repository import session_scope
from .Security import hash_password, valid_csrf_token, verify_password


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.password_confirmation:
            raise ValueError("New passwords do not match.")
        return self


class AccountController(Controller):
    path = "/Account"

    @get("/Password")
    async def password_page(self, request: Request) -> Template:
        return self._render(request)

    @post("/Password")
    async def change_password(self, request: Request) -> Template | Redirect:
        form = await request.form()
        errors: dict[str, str] = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            errors["form"] = "This form expired. Refresh and try again."
        try:
            data = PasswordChange.model_validate(clean_form(form))
        except ValidationError as exc:
            errors.update(form_errors(exc))
            data = None
        if data and not errors:
            with session_scope() as session:
                user = session.get(type(request.user), request.user.id)
                if not user or not verify_password(data.current_password, user.password_hash):
                    errors["current_password"] = "Current password is incorrect."
                else:
                    user.password_hash = hash_password(data.password)
                    user.must_change_password = False
                    user.session_version += 1
                    session.flush()
                    request.session["session_version"] = user.session_version
            if not errors:
                request.session["flash"] = "Password changed successfully."
                return Redirect("/Dashboard", status_code=303)
        return self._render(request, errors, 422)

    @staticmethod
    def _render(request: Request, errors=None, status_code=200) -> Template:
        return Template("Authentication/Password.html", context={
            **page_context(request, "Change password", "", "Account security"),
            "errors": errors or {},
            "forced": request.user.must_change_password,
        }, status_code=status_code)
