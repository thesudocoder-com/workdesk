from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Response, Template
from pydantic import ValidationError

from Application.Authentication.Guards import outreach_or_developer
from Application.Authentication.Security import valid_csrf_token
from Application.Common.Enums import ClientStatus
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import form_context, page_context, redirect_after
from .Schemas import ClientCreate, ClientUpdate
from .Service import ClientService


PROVINCES = ["Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba", "Saskatchewan", "Nova Scotia", "New Brunswick", "Newfoundland and Labrador", "Prince Edward Island", "Northwest Territories", "Nunavut", "Yukon"]


def client_fields() -> list[dict]:
    return [
        {"name": "name", "label": "Primary contact", "type": "text", "required": True, "placeholder": "Jane Smith"},
        {"name": "company_name", "label": "Company name", "type": "text", "required": False, "placeholder": "Acme Corporation"},
        {"name": "legal_name", "label": "Legal name", "type": "text", "required": False, "placeholder": "Acme Corporation Inc."},
        {"name": "default_currency", "label": "Default currency", "type": "text", "required": True, "placeholder": "CAD"},
        {"name": "tax_identifiers", "label": "Tax identifiers", "type": "textarea", "required": False, "wide": True},
        {"name": "primary_email", "label": "Email", "type": "email", "required": False, "placeholder": "jane@acme.ca"},
        {"name": "primary_phone", "label": "Phone", "type": "tel", "required": False, "placeholder": "+1 416 555 0123"},
        {"name": "website", "label": "Website", "type": "url", "required": False, "placeholder": "https://acme.ca"},
        {"name": "status", "label": "Status", "type": "select", "options": [item.value for item in ClientStatus], "required": True},
        {"name": "address_line1", "label": "Address", "type": "text", "required": False, "wide": True, "placeholder": "123 King Street West"},
        {"name": "city", "label": "City", "type": "text", "required": False, "placeholder": "Toronto"},
        {"name": "province", "label": "Province", "type": "select", "options": PROVINCES, "required": False},
        {"name": "postal_code", "label": "Postal code", "type": "text", "required": False, "placeholder": "M5H 1J9"},
        {"name": "notes", "label": "Internal notes", "type": "textarea", "required": False, "wide": True, "placeholder": "Context, preferences, or relationship notes"},
    ]


class ClientsController(Controller):
    path = "/Clients"

    @get()
    async def index(self, request: Request, q: FromQuery[str] = "", status: FromQuery[str] = "") -> Template:
        clients = ClientService().list(q, status)
        context = {**page_context(request, "Clients", "clients", "Relationships"), "clients": clients, "query": q, "selected_status": status, "statuses": list(ClientStatus)}
        return Template("Clients/_Table.html" if request.headers.get("HX-Request") else "Clients/Index.html", context=context)

    @get("/New", guards=[outreach_or_developer])
    async def new(self, request: Request) -> Template:
        context = form_context(request, title="New client", subtitle="Add an organization and its primary contact details.", section="clients", action="/Clients", cancel_url="/Clients", fields=client_fields(), values={"status": ClientStatus.ACTIVE.value, "country": "Canada", "default_currency": "CAD"})
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context)

    @post(guards=[outreach_or_developer])
    async def create(self, request: Request) -> Template | Redirect:
        form = await request.form(); values = dict(form)
        errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired. Refresh and try again."
        try: data = ClientCreate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data = None
        if errors:
            context = form_context(request, title="New client", subtitle="Add a client and their primary contact details.", section="clients", action="/Clients", cancel_url="/Clients", fields=client_fields(), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        client = ClientService().create(data, request.user.id)
        request.session["flash"] = f"{client.display_name} was added."
        return redirect_after(request, f"/Clients/{client.id}")

    @get("/{client_id:int}")
    async def detail(self, request: Request, client_id: FromPath[int]) -> Template | Redirect:
        detail = ClientService().detail(client_id)
        if not detail:
            request.session["error"] = "Client not found."; return Redirect("/Clients")
        return Template("Clients/Detail.html", context={**page_context(request, detail["client"].display_name, "clients", "Client workspace"), **detail})

    @get("/{client_id:int}/Edit", guards=[outreach_or_developer])
    async def edit(self, request: Request, client_id: FromPath[int]) -> Template | Redirect:
        client = ClientService().get(client_id)
        if not client:
            return Redirect("/Clients")
        values = {field["name"]: getattr(client, field["name"], "") or "" for field in client_fields()}
        context = form_context(request, title="Edit client", subtitle=f"Update {client.display_name}'s contact and account details.", section="clients", action=f"/Clients/{client.id}/Edit", cancel_url=f"/Clients/{client.id}", fields=client_fields(), values=values)
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context)

    @post("/{client_id:int}/Edit", guards=[outreach_or_developer])
    async def update(self, request: Request, client_id: FromPath[int]) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired."
        try: data = ClientUpdate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data = None
        if errors:
            context = form_context(request, title="Edit client", subtitle="Correct the highlighted fields.", section="clients", action=f"/Clients/{client_id}/Edit", cancel_url=f"/Clients/{client_id}", fields=client_fields(), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        ClientService().update(client_id, data, request.user.id); request.session["flash"] = "Client updated."
        return redirect_after(request, f"/Clients/{client_id}")

    @post("/{client_id:int}/Delete", guards=[outreach_or_developer])
    async def delete(self, request: Request, client_id: FromPath[int]) -> Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired. Please refresh and try again."
            return redirect_after(request, "/Clients")
        try:
            ClientService().delete(client_id, request.user.id)
            request.session["flash"] = "Client deleted."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return redirect_after(request, "/Clients")
