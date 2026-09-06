from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Template
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from Application.Authentication.Security import valid_csrf_token
from Application.Common.Enums import Priority, TaskStatus
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Views import form_context, page_context, redirect_after
from Application.Projects.Service import ProjectService
from Application.Users.Service import UserService
from .Schemas import TaskCreate, TaskStatusUpdate
from .Service import TaskService


def task_fields() -> list[dict]:
    projects=[p for p in ProjectService().list() if p.status not in {"Completed","Cancelled"}];users=[u for u in UserService().list_users() if u.is_active]
    return [
        {"name":"project_id","label":"Project","type":"select","options":[(p.id,f"{p.name} — {p.engagement.client.display_name}") for p in projects],"required":True,"wide":True},
        {"name":"title","label":"Task title","type":"text","required":True,"placeholder":"Review homepage revision","wide":True},
        {"name":"assigned_to_id","label":"Assignee","type":"select","options":[(u.id,u.name) for u in users],"required":False},
        {"name":"status","label":"Status","type":"select","options":[x.value for x in TaskStatus],"required":True},
        {"name":"priority","label":"Priority","type":"select","options":[x.value for x in Priority],"required":True},
        {"name":"due_date","label":"Due date","type":"date","required":False},
        {"name":"description","label":"Description","type":"textarea","required":False,"wide":True},
    ]


class TasksController(Controller):
    path="/Tasks"

    @get()
    async def index(self,request:Request,q:FromQuery[str]="",status:FromQuery[str]="",scope:FromQuery[str]="my")->Template:
        assignee=request.user.id if scope=="my" else None;tasks=TaskService().list(q,status,assignee)
        context={**page_context(request,"Tasks","tasks","Your work"),"tasks":tasks,"query":q,"selected_status":status,"scope":scope,"statuses":list(TaskStatus),"today":__import__("Application.Common.Time",fromlist=["today_toronto"]).today_toronto()}
        return Template("Tasks/_Table.html" if request.headers.get("HX-Request") else "Tasks/Index.html",context=context)

    @get("/New")
    async def new(self,request:Request,project_id:FromQuery[int|None]=None)->Template:
        has_projects = any(p.status not in {"Completed","Cancelled"} for p in ProjectService().list())
        context=form_context(request,title="New task",subtitle="Add a concrete next step to a project.",section="tasks",action="/Tasks",cancel_url="/Tasks",fields=task_fields(),values={"project_id":project_id or "","status":TaskStatus.TODO.value,"priority":Priority.MEDIUM.value,"assigned_to_id":request.user.id},prerequisite=None if has_projects else {"title":"Create a project first","message":"Tasks need an open project.","url":"/Projects/New","action":"Start guided project setup"})
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context)

    @post()
    async def create(self,request:Request)->Template|Redirect:
        form=await request.form();values=dict(form);errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")):errors["form"]="This form expired. Refresh and try again."
        try:data=TaskCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if errors:
            context=form_context(request,title="New task",subtitle="Add a concrete next step to a project.",section="tasks",action="/Tasks",cancel_url="/Tasks",fields=task_fields(),values=values,errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context,status_code=422)
        try: TaskService().create(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            context=form_context(request,title="New task",subtitle="Correct the highlighted fields.",section="tasks",action="/Tasks",cancel_url="/Tasks",fields=task_fields(),values=values,errors=errors)
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context,status_code=422)
        request.session["flash"]="Task created."
        return redirect_after(request,"/Tasks")

    @post("/{task_id:int}/Status")
    async def status(self, request: Request, task_id: FromPath[int]) -> Redirect:
        form = await request.form()
        target_url = request.headers.get("Referer") or "/Tasks"
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired."
            return Redirect(target_url, status_code=303)
        try:
            TaskService().update_status(task_id, TaskStatusUpdate.model_validate({"status": form.get("status")}), request.user.id)
            request.session["flash"] = "Task status updated."
        except (ValidationError, ValueError) as exc:
            request.session["error"] = str(exc)
        return Redirect(target_url, status_code=303)
