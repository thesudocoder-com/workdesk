from datetime import datetime

from litestar import Controller, Request, get
from litestar.response import Template

from Application.Common.Time import business_timezone
from Application.Common.Views import page_context
from Application.Users.Models import UserRole
from .Service import DashboardService


class DashboardController(Controller):
    path = "/Dashboard"

    @get()
    async def dashboard(self, request: Request) -> Template:
        now = datetime.now(business_timezone())
        greeting = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"
        return Template(
            "Dashboard/Index.html",
            context={
                **page_context(request, "Today", "dashboard", now.strftime("%A, %d %B")),
                "today_label": now.strftime("%A · %d %B").replace("· 0", "· "),
                "greeting": greeting,
                **DashboardService().get(
                    request.user.id,
                    request.user.role in {
                        UserRole.DEVELOPER.value,
                        UserRole.OUTREACH_MANAGER.value,
                    },
                ),
            },
        )
