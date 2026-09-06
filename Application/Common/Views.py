from litestar import Request
from litestar.response import Redirect, Response

from Application.Authentication.Security import get_csrf_token
from Application.Settings.Service import get_workspace


def page_context(request: Request, title: str, section: str, eyebrow: str = "WorkDesk") -> dict:
    workspace = get_workspace()
    return {
        "page_title": title,
        "page_eyebrow": eyebrow,
        "current_section": section,
        "current_user": request.user,
        "csrf_token": get_csrf_token(request.session),
        "flash": request.session.pop("flash", None),
        "error": request.session.pop("error", None),
        "workspace": workspace,
        "business_name": workspace.business_name if workspace else "WorkDesk",
        "currency": workspace.currency if workspace else "USD",
    }


def form_context(
    request: Request,
    *,
    title: str,
    subtitle: str,
    section: str,
    action: str,
    cancel_url: str,
    fields: list[dict],
    values: dict | None = None,
    errors: dict | None = None,
    prerequisite: dict | None = None,
) -> dict:
    return {
        **page_context(request, title, section, "Create record"),
        "form_title": title,
        "form_subtitle": subtitle,
        "form_action": action,
        "cancel_url": cancel_url,
        "fields": fields,
        "values": values or {},
        "errors": errors or {},
        "prerequisite": prerequisite,
    }


def redirect_after(request: Request, path: str) -> Redirect | Response:
    if request.headers.get("HX-Request"):
        return Response(content="", status_code=204, headers={"HX-Redirect": path})
    return Redirect(path, status_code=303)
