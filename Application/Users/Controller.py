from __future__ import annotations

from litestar import Controller, Request, get, post
from litestar.response import Redirect, Response, Template
from litestar.params import FromPath, FromQuery
from pydantic import ValidationError

from Application.Authentication.Guards import developer_only
from Application.Authentication.Security import get_csrf_token, valid_csrf_token
from .Models import UserRole
from .Schemas import PasswordReset, UserCreate, UserRoleUpdate
from .Service import UserConflictError, UserRuleError, UserService


class UsersController(Controller):
    path = "/Users"
    guards = [developer_only]

    @get()
    async def users(
        self,
        request: Request,
        q: FromQuery[str] = "",
        role: FromQuery[str] = "",
        status: FromQuery[str] = "",
    ) -> Template:
        service = UserService()
        users = service.list_users(q, role, status)
        all_users = service.list_users()
        context = {
            "page_title": "Team",
            "page_eyebrow": "Workspace management",
            "current_section": "team",
            "current_user": request.user,
            "csrf_token": get_csrf_token(request.session),
            "users": users,
            "query": q,
            "selected_role": role,
            "selected_status": status,
            "roles": list(UserRole),
            "total_count": len(all_users),
            "active_count": sum(user.is_active for user in all_users),
            "admin_count": sum(user.role == UserRole.DEVELOPER.value for user in all_users),
            "flash": request.session.pop("flash", None),
            "error": request.session.pop("error", None),
        }
        template = "Users/_Table.html" if request.headers.get("HX-Request") else "Users/Index.html"
        return Template(template, context=context)

    @get("/New")
    async def new_user(self, request: Request) -> Template:
        context = self._form_context(request, mode="create")
        template = "Users/_Form.html" if request.headers.get("HX-Request") else "Users/Form.html"
        return Template(template, context=context)

    @post()
    async def create_user(self, request: Request) -> Template | Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            return self._form_error(request, "This form expired. Please try again.", form, 400)
        try:
            data = UserCreate.model_validate(dict(form))
            UserService().create_user(data)
        except ValidationError as exc:
            return self._form_error(request, self._validation_message(exc), form, 422)
        except UserConflictError as exc:
            return self._form_error(request, str(exc), form, 409)

        request.session["flash"] = "Team member added successfully."
        if request.headers.get("HX-Request"):
            return Response(content="", status_code=204, headers={"HX-Redirect": "/Users"})
        return Redirect("/Users", status_code=303)

    @post("/{user_id:int}/Role")
    async def update_role(self, request: Request, user_id: FromPath[int]) -> Redirect:
        form = await request.form()
        try:
            self._require_csrf(request, form.get("csrf_token"))
            UserService().update_role(
                user_id,
                UserRoleUpdate.model_validate({"role": form.get("role")}),
                request.user.id,
            )
            request.session["flash"] = "Role updated."
        except (ValidationError, UserRuleError) as exc:
            request.session["error"] = str(exc)
        return Redirect("/Users", status_code=303)

    @post("/{user_id:int}/Status")
    async def toggle_status(self, request: Request, user_id: FromPath[int]) -> Redirect:
        form = await request.form()
        try:
            self._require_csrf(request, form.get("csrf_token"))
            user = UserService().toggle_status(user_id, request.user.id)
            request.session["flash"] = f"{user.name} is now {'active' if user.is_active else 'inactive'}."
        except UserRuleError as exc:
            request.session["error"] = str(exc)
        return Redirect("/Users", status_code=303)

    @get("/{user_id:int}/ResetPassword")
    async def reset_password_form(self, request: Request, user_id: FromPath[int]) -> Template:
        users = UserService().list_users()
        user = next((item for item in users if item.id == user_id), None)
        if not user:
            request.session["error"] = "User not found."
            return Redirect("/Users")
        context = self._form_context(request, mode="reset", target_user=user)
        template = "Users/_Form.html" if request.headers.get("HX-Request") else "Users/Form.html"
        return Template(template, context=context)

    @post("/{user_id:int}/ResetPassword")
    async def reset_password(
        self, request: Request, user_id: FromPath[int]
    ) -> Template | Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            return self._form_error(request, "This form expired. Please try again.", form, 400, "reset")
        try:
            UserService().reset_password(
                user_id, PasswordReset.model_validate({"password": form.get("password"), "password_confirmation": form.get("password_confirmation")})
            )
        except ValidationError as exc:
            return self._form_error(
                request,
                self._validation_message(exc),
                form,
                422,
                "reset",
                UserService().get_user(user_id),
            )
        except UserRuleError as exc:
            request.session["error"] = str(exc)
            return Redirect("/Users", status_code=303)
        request.session["flash"] = "Password reset successfully."
        if request.headers.get("HX-Request"):
            return Response(content="", status_code=204, headers={"HX-Redirect": "/Users"})
        return Redirect("/Users", status_code=303)

    @staticmethod
    def _require_csrf(request: Request, token: str | None) -> None:
        if not valid_csrf_token(request.session, token):
            raise UserRuleError("This form expired. Please refresh and try again.")

    @staticmethod
    def _validation_message(exc: ValidationError) -> str:
        first = exc.errors()[0]
        field = str(first.get("loc", ["Field"])[0]).replace("_", " ").capitalize()
        return f"{field}: {first.get('msg', 'is invalid')}"

    @staticmethod
    def _form_context(request: Request, **extra) -> dict:
        return {
            "page_title": "Team",
            "page_eyebrow": "Workspace management",
            "current_section": "team",
            "current_user": request.user,
            "csrf_token": get_csrf_token(request.session),
            "roles": list(UserRole),
            "form_data": {},
            "error": None,
            **extra,
        }

    def _form_error(
        self,
        request: Request,
        error: str,
        form,
        status_code: int,
        mode: str = "create",
        target_user=None,
    ) -> Template:
        context = self._form_context(
            request, mode=mode, error=error, form_data=dict(form), target_user=target_user
        )
        template = "Users/_Form.html" if request.headers.get("HX-Request") else "Users/Form.html"
        return Template(template, context=context, status_code=status_code)
