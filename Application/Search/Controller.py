from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from litestar import Controller, Request, get
from litestar.params import FromQuery
from litestar.response import Template

from Application.Clients.Models import Client
from Application.Finance.Models import Invoice
from Application.Projects.Models import Project
from Application.Tasks.Models import WorkTask
from Application.Users.Repository import session_scope


class SearchController(Controller):
    path = "/Search"

    @get()
    async def search(self, request: Request, q: FromQuery[str] = "") -> Template:
        results = {"clients": [], "projects": [], "tasks": [], "invoices": []}
        if len(q.strip()) >= 2:
            term = f"%{q.lower().strip()}%"
            with session_scope() as session:
                results["clients"] = list(session.scalars(select(Client).where(func.lower(Client.name).like(term) | func.lower(Client.company_name).like(term)).limit(5)))
                results["projects"] = list(session.scalars(select(Project).where(func.lower(Project.name).like(term)).options(selectinload(Project.engagement)).limit(5)))
                results["tasks"] = list(session.scalars(select(WorkTask).where(func.lower(WorkTask.title).like(term)).options(selectinload(WorkTask.project)).limit(5)))
                results["invoices"] = list(session.scalars(select(Invoice).where(func.lower(Invoice.invoice_number).like(term)).options(selectinload(Invoice.client), selectinload(Invoice.payments)).limit(5)))
        return Template("Search/Results.html", context={"query": q, **results})
