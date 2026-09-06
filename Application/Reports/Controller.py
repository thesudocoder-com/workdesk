from litestar import Controller, Request, get
from litestar.response import Template

from Application.Authentication.Guards import outreach_or_developer
from Application.Common.Views import page_context
from .Service import ReportsService


class ReportsController(Controller):
    path="/Reports"
    guards=[outreach_or_developer]

    @get()
    async def index(self,request:Request)->Template:
        return Template("Reports/Index.html",context={**page_context(request,"Reports","reports","Performance"),**ReportsService().get()})
