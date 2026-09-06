from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Response, Template
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from Application.Authentication.Guards import outreach_or_developer
from Application.Authentication.Security import valid_csrf_token
from Application.Clients.Service import ClientService
from Application.Common.Enums import BillingFrequency, EngagementStatus, EngagementType
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import form_context, page_context, redirect_after
from Application.Users.Service import UserService
from Application.Settings.Service import get_workspace
from .Schemas import EngagementCreate, EngagementUpdate
from .Service import EngagementService


def engagement_fields() -> list[dict]:
    clients = ClientService().list(status="Active"); users = [u for u in UserService().list_users() if u.is_active]
    currency = get_workspace().currency
    return [
        {"name":"client_id","label":"Client","type":"select","options":[(c.id,c.display_name) for c in clients],"required":True,"wide":True},
        {"name":"name","label":"Engagement name","type":"text","required":True,"placeholder":"Website redesign","wide":True},
        {"name":"type","label":"Type","type":"select","options":[x.value for x in EngagementType],"required":True},
        {"name":"owner_id","label":"Owner","type":"select","options":[(u.id,u.name) for u in users],"required":True},
        {"name":"contract_value","label":f"Contract value ({currency})","type":"number","step":"0.01","required":True,"placeholder":"18000.00"},
        {"name":"billing_frequency","label":"Billing frequency","type":"select","options":[x.value for x in BillingFrequency],"required":True},
        {"name":"start_date","label":"Start date","type":"date","required":False},
        {"name":"end_date","label":"Target completion","type":"date","required":False},
        {"name":"status","label":"Status","type":"select","options":[x.value for x in EngagementStatus],"required":True},
        {"name":"description","label":"Scope and notes","type":"textarea","required":False,"wide":True},
    ]


class EngagementsController(Controller):
    path = "/Engagements"

    @get()
    async def index(self, request: Request, q: FromQuery[str]="", status: FromQuery[str]="") -> Template:
        items=EngagementService().list(q,status); context={**page_context(request,"Engagements","engagements","Commercial work"),"engagements":items,"query":q,"selected_status":status,"statuses":list(EngagementStatus)}
        return Template("Engagements/_Table.html" if request.headers.get("HX-Request") else "Engagements/Index.html",context=context)

    @get("/New", guards=[outreach_or_developer])
    async def new(self, request: Request, client_id: FromQuery[int|None]=None) -> Template:
        has_clients = bool(ClientService().list(status="Active"))
        context=form_context(request,title="New engagement",subtitle="Define the commercial agreement, ownership, dates, and value.",section="engagements",action="/Engagements",cancel_url="/Engagements",fields=engagement_fields(),values={"client_id":client_id or "","currency":get_workspace().currency,"status":EngagementStatus.ACTIVE.value,"billing_frequency":BillingFrequency.ONE_TIME.value},prerequisite=None if has_clients else {"title":"Add a client first","message":"Every engagement must belong to an active client.","url":"/Clients/New","action":"Create client"})
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context)

    @post(guards=[outreach_or_developer])
    async def create(self, request: Request) -> Template|Redirect:
        form=await request.form(); values=dict(form); errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")): errors["form"]="This form expired. Refresh and try again."
        try: data=EngagementCreate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data=None
        if errors:
            context=form_context(request,title="New engagement",subtitle="Define the commercial agreement, ownership, dates, and value.",section="engagements",action="/Engagements",cancel_url="/Engagements",fields=engagement_fields(),values=values,errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context,status_code=422)
        try: item=EngagementService().create(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            context=form_context(request,title="New engagement",subtitle="Correct the highlighted fields.",section="engagements",action="/Engagements",cancel_url="/Engagements",fields=engagement_fields(),values=values,errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context,status_code=422)
        request.session["flash"]="Engagement created."
        return redirect_after(request,f"/Engagements/{item.id}")

    @get("/{engagement_id:int}")
    async def detail(self, request: Request, engagement_id: FromPath[int]) -> Template|Redirect:
        item=EngagementService().get(engagement_id)
        if not item: request.session["error"]="Engagement not found."; return Redirect("/Engagements")
        collected=sum((invoice.amount_paid for invoice in item.invoices),0); outstanding=sum((invoice.outstanding for invoice in item.invoices),0)
        return Template("Engagements/Detail.html",context={**page_context(request,item.name,"engagements","Engagement"),"engagement":item,"collected":collected,"outstanding":outstanding})

    @get("/{engagement_id:int}/Edit", guards=[outreach_or_developer])
    async def edit(self, request: Request, engagement_id: FromPath[int]) -> Template | Redirect:
        item = EngagementService().get(engagement_id)
        if not item:
            return Redirect("/Engagements")
        values = {field["name"]: getattr(item, field["name"], "") or "" for field in engagement_fields()}
        context = form_context(request, title="Edit engagement", subtitle=f"Update {item.name}'s details.", section="engagements", action=f"/Engagements/{item.id}/Edit", cancel_url=f"/Engagements/{item.id}", fields=engagement_fields(), values=values)
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context)

    @post("/{engagement_id:int}/Edit", guards=[outreach_or_developer])
    async def update(self, request: Request, engagement_id: FromPath[int]) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired."
        try: data = EngagementUpdate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data = None
        if errors:
            context = form_context(request, title="Edit engagement", subtitle="Correct the highlighted fields.", section="engagements", action=f"/Engagements/{engagement_id}/Edit", cancel_url=f"/Engagements/{engagement_id}", fields=engagement_fields(), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        try:
            EngagementService().update(engagement_id, data, request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            context = form_context(request, title="Edit engagement", subtitle="Correct the highlighted fields.", section="engagements", action=f"/Engagements/{engagement_id}/Edit", cancel_url=f"/Engagements/{engagement_id}", fields=engagement_fields(), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        request.session["flash"] = "Engagement updated."
        return redirect_after(request, f"/Engagements/{engagement_id}")

    @post("/{engagement_id:int}/Delete", guards=[outreach_or_developer])
    async def delete(self, request: Request, engagement_id: FromPath[int]) -> Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired. Please refresh and try again."
            return redirect_after(request, "/Engagements")
        try:
            EngagementService().delete(engagement_id, request.user.id)
            request.session["flash"] = "Engagement deleted."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return redirect_after(request, "/Engagements")

