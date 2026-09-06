from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Response, Template
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from Application.Authentication.Guards import developer_only, outreach_or_developer
from Application.Authentication.Security import valid_csrf_token
from Application.Common.Enums import EngagementStatus, Priority, ProjectStatus
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import form_context, page_context, redirect_after
from Application.Engagements.Service import EngagementService
from Application.Clients.Schemas import ClientCreate
from Application.Clients.Service import ClientService
from Application.Engagements.Schemas import EngagementCreate
from Application.Common.Enums import BillingFrequency, EngagementType
from Application.Settings.Service import get_workspace
from Application.Users.Service import UserService
from .Schemas import ProjectCreate, ProjectUpdate
from .Service import ProjectService


def project_fields(include_all_statuses: bool = True) -> list[dict]:
    engagements = EngagementService().list()
    active_engagements = [e for e in engagements if e.status == EngagementStatus.ACTIVE.value]

    engagement_options = []
    for e in active_engagements:
        client_name = e.client.display_name if e.client else "Client"
        engagement_options.append((e.id, f"{client_name} — {e.name}"))

    users = [u for u in UserService().list_users() if u.is_active]
    owner_options = [(u.id, u.name) for u in users]
    status_options = [x.value for x in ProjectStatus] if include_all_statuses else [x.value for x in ProjectStatus if x not in {ProjectStatus.COMPLETED, ProjectStatus.CANCELLED}]

    return [
        {
            "name": "engagement_id",
            "label": "Engagement",
            "type": "select",
            "options": engagement_options,
            "required": True,
            "wide": True,
        },
        {
            "name": "name",
            "label": "Project name",
            "type": "text",
            "required": True,
            "placeholder": "Website redesign",
            "wide": True,
        },
        {
            "name": "owner_id",
            "label": "Owner",
            "type": "select",
            "options": owner_options,
            "required": True,
        },
        {
            "name": "status",
            "label": "Status",
            "type": "select",
            "options": status_options,
            "required": True,
        },
        {
            "name": "priority",
            "label": "Priority",
            "type": "select",
            "options": [x.value for x in Priority],
            "required": True,
        },
        {
            "name": "start_date",
            "label": "Start date",
            "type": "date",
            "required": False,
        },
        {
            "name": "due_date",
            "label": "Due date",
            "type": "date",
            "required": False,
        },
        {
            "name": "description",
            "label": "Project brief",
            "type": "textarea",
            "required": False,
            "wide": True,
            "placeholder": "Scope, milestones, or deliverables",
        },
    ]


class ProjectsController(Controller):
    path="/Projects"

    @get()
    async def index(self,request:Request,q:FromQuery[str]="",status:FromQuery[str]="",owner_id:FromQuery[int|None]=None)->Template:
        projects=ProjectService().list(q,status,owner_id); users=[u for u in UserService().list_users() if u.is_active]
        context={**page_context(request,"Projects","projects","Delivery"),"projects":projects,"query":q,"selected_status":status,"selected_owner":owner_id,"statuses":list(ProjectStatus),"owners":users}
        return Template("Projects/_Table.html" if request.headers.get("HX-Request") else "Projects/Index.html",context=context)

    @get("/New", guards=[outreach_or_developer])
    async def new(self, request: Request, engagement_id: FromQuery[int | None] = None, client_id: FromQuery[int | None] = None) -> Template:
        engagement = EngagementService().get(engagement_id) if engagement_id else None
        if engagement and engagement.status == EngagementStatus.ACTIVE.value:
            client_id = engagement.client_id
            step = 3
        elif client_id and ClientService().get(client_id):
            step = 2
            engagement_id = None
        else:
            step = 1
            client_id = engagement_id = None
        return self._wizard(request, step, client_id=client_id, engagement_id=engagement_id)

    @post("/New/Client", guards=[outreach_or_developer])
    async def wizard_client(self, request: Request) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired."
        client_id = None
        if form.get("client_id"):
            try: client_id = int(form.get("client_id"))
            except (TypeError, ValueError): errors["client_id"] = "Select a valid client."
            if client_id and not ClientService().get(client_id): errors["client_id"] = "That client is no longer available."
        else:
            try:
                data = ClientCreate.model_validate(clean_form(form))
            except ValidationError as exc: errors.update(form_errors(exc)); data = None
            if data and not errors: client_id = ClientService().create(data, request.user.id).id
        if errors: return self._wizard(request, 1, values=values, errors=errors, status_code=422)
        return Redirect(f"/Projects/New?client_id={client_id}", status_code=303)

    @post("/New/Engagement", guards=[outreach_or_developer])
    async def wizard_engagement(self, request: Request) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired."
        try: client_id = int(form.get("client_id"))
        except (TypeError, ValueError): client_id = 0
        client = ClientService().get(client_id)
        if not client: errors["client_id"] = "That client is no longer available."
        engagement_id = None
        if form.get("engagement_id"):
            try: engagement_id = int(form.get("engagement_id"))
            except (TypeError, ValueError): errors["engagement_id"] = "Select a valid engagement."
            engagement = EngagementService().get(engagement_id) if engagement_id else None
            if not engagement or engagement.client_id != client_id or engagement.status != EngagementStatus.ACTIVE.value:
                errors["engagement_id"] = "Select an active engagement belonging to this client."
        else:
            payload = clean_form(form); payload["client_id"] = client_id; payload["owner_id"] = request.user.id; payload["currency"] = get_workspace().currency
            try: data = EngagementCreate.model_validate(payload)
            except ValidationError as exc: errors.update(form_errors(exc)); data = None
            if data and not errors:
                try: engagement_id = EngagementService().create(data, request.user.id).id
                except (ValueError, IntegrityError) as exc: errors["form"] = str(exc) if isinstance(exc,ValueError) else "A selected record changed. Refresh and try again."
        if errors: return self._wizard(request, 2, client_id=client_id, values=values, errors=errors, status_code=422)
        return Redirect(f"/Projects/New?engagement_id={engagement_id}", status_code=303)

    @post(guards=[outreach_or_developer])
    async def create(self,request:Request)->Template|Redirect:
        form=await request.form(); values=dict(form); errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")): errors["form"]="This form expired. Refresh and try again."
        try:data=ProjectCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if errors:
            engagement_id = int(values.get("engagement_id", 0) or 0)
            engagement = EngagementService().get(engagement_id)
            return self._wizard(request,3,client_id=engagement.client_id if engagement else None,engagement_id=engagement_id,values=values,errors=errors,status_code=422)
        try: project=ProjectService().create(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            engagement_id = int(values.get("engagement_id", 0) or 0)
            engagement = EngagementService().get(engagement_id)
            return self._wizard(request,3,client_id=engagement.client_id if engagement else None,engagement_id=engagement_id,values=values,errors=errors,status_code=422)
        request.session["flash"]="Project created."
        return redirect_after(request,f"/Projects/{project.id}")

    @staticmethod
    def _wizard(request: Request, step: int, *, client_id=None, engagement_id=None, values=None, errors=None, status_code=200) -> Template:
        clients = ClientService().list(status="Active")
        client = ClientService().get(client_id) if client_id else None
        engagements = [e for e in EngagementService().list(status="Active") if e.client_id == client_id]
        engagement = EngagementService().get(engagement_id) if engagement_id else None
        users = [u for u in UserService().list_users() if u.is_active]
        defaults = {"status": ProjectStatus.PLANNING.value,"priority": Priority.MEDIUM.value,"owner_id": request.user.id,"type": EngagementType.CONSULTING.value,"billing_frequency": BillingFrequency.ONE_TIME.value,"contract_value":"0.00"}
        defaults.update(values or {})
        return Template("Projects/Wizard.html", context={**page_context(request,"New project","projects","Guided setup"),"step":step,"clients":clients,"client":client,"engagements":engagements,"engagement":engagement,"owners":users,"values":defaults,"errors":errors or {},"engagement_types":list(EngagementType),"billing_frequencies":list(BillingFrequency),"project_statuses":[x for x in ProjectStatus if x not in {ProjectStatus.COMPLETED,ProjectStatus.CANCELLED}],"priorities":list(Priority)}, status_code=status_code)

    @get("/{project_id:int}")
    async def detail(self,request:Request,project_id:FromPath[int])->Template|Redirect:
        project=ProjectService().get(project_id)
        if not project:request.session["error"]="Project not found.";return Redirect("/Projects")
        from Application.Common.Time import today_toronto
        return Template("Projects/Detail.html",context={**page_context(request,project.name,"projects","Project workspace"),"project":project,"today":today_toronto(),"hide_task_project":True})

    @get("/{project_id:int}/Edit", guards=[outreach_or_developer])
    async def edit(self, request: Request, project_id: FromPath[int]) -> Template | Redirect:
        project = ProjectService().get(project_id)
        if not project:
            return Redirect("/Projects")
        values = {field["name"]: getattr(project, field["name"], "") or "" for field in project_fields(include_all_statuses=True)}
        context = form_context(request, title="Edit project", subtitle=f"Update {project.name}'s details.", section="projects", action=f"/Projects/{project.id}/Edit", cancel_url=f"/Projects/{project.id}", fields=project_fields(include_all_statuses=True), values=values)
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context)

    @post("/{project_id:int}/Edit", guards=[outreach_or_developer])
    async def update(self, request: Request, project_id: FromPath[int]) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        if not valid_csrf_token(request.session, form.get("csrf_token")): errors["form"] = "This form expired."
        try: data = ProjectUpdate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data = None
        if errors:
            context = form_context(request, title="Edit project", subtitle="Correct the highlighted fields.", section="projects", action=f"/Projects/{project_id}/Edit", cancel_url=f"/Projects/{project_id}", fields=project_fields(include_all_statuses=True), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        try:
            ProjectService().update(project_id, data, request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            context = form_context(request, title="Edit project", subtitle="Correct the highlighted fields.", section="projects", action=f"/Projects/{project_id}/Edit", cancel_url=f"/Projects/{project_id}", fields=project_fields(include_all_statuses=True), values=values, errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html", context=context, status_code=422)
        request.session["flash"] = "Project updated."
        return redirect_after(request, f"/Projects/{project_id}")

    @post("/{project_id:int}/Delete", guards=[outreach_or_developer])
    async def delete(self, request: Request, project_id: FromPath[int]) -> Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired. Please refresh and try again."
            return redirect_after(request, "/Projects")
        try:
            ProjectService().delete(project_id, request.user.id)
            request.session["flash"] = "Project deleted."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return redirect_after(request, "/Projects")

    @post("/{project_id:int}/Complete", guards=[developer_only])
    async def complete(self, request: Request, project_id: FromPath[int]) -> Redirect:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired. Please refresh and try again."
            return Redirect(f"/Projects/{project_id}", status_code=303)
        try:
            ProjectService().complete(project_id, request.user.id)
            request.session["flash"] = "Project marked complete."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return Redirect(f"/Projects/{project_id}", status_code=303)

