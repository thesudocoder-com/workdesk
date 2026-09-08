from __future__ import annotations

from calendar import Calendar
from datetime import date

from litestar import Controller, Request, get
from litestar.params import FromQuery
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from Application.Authentication.Guards import outreach_or_developer
from Application.Clients.Models import Client
from Application.Clients.Service import ClientService
from Application.Common.Time import today_toronto
from Application.Common.Views import page_context
from Application.Engagements.Models import Engagement
from Application.Engagements.Service import EngagementService
from Application.Finance.Models import (
    BillingOccurrence, FixedFeeAgreement, Instalment, Invoice, RecurringService,
)
from Application.Finance.Service import FinanceService
from Application.Projects.Models import Project
from Application.Projects.Service import ProjectService
from Application.Users.Repository import session_scope


def _selected_month(value: str) -> date:
    try:
        selected = date.fromisoformat(f"{value}-01")
    except ValueError:
        selected = today_toronto().replace(day=1)
    return selected


def _shift_month(value: date, amount: int) -> date:
    month_index = value.month - 1 + amount
    return date(value.year + month_index // 12, month_index % 12 + 1, 1)


class CalendarController(Controller):
    path = "/Calendar"
    guards = [outreach_or_developer]

    @get()
    async def index(
        self,
        request: Request,
        month: FromQuery[str] = "",
        client_id: FromQuery[int | None] = None,
        engagement_id: FromQuery[int | None] = None,
        project_id: FromQuery[int | None] = None,
        view: FromQuery[str] = "month",
    ) -> Template:
        selected = _selected_month(month)
        weeks = Calendar(firstweekday=0).monthdatescalendar(selected.year, selected.month)
        grid_start, grid_end = weeks[0][0], weeks[-1][-1]
        FinanceService().forecast_recurring(grid_end)
        events: list[dict] = []

        with session_scope() as session:
            instalment_query = (
                select(Instalment)
                .join(Instalment.agreement)
                .join(Engagement)
                .where(Instalment.due_date >= grid_start, Instalment.due_date <= grid_end)
                .options(selectinload(Instalment.agreement)
                         .selectinload(FixedFeeAgreement.engagement)
                         .selectinload(Engagement.client))
            )
            occurrence_query = (
                select(BillingOccurrence)
                .join(BillingOccurrence.service)
                .join(Engagement)
                .where(
                    BillingOccurrence.billing_date >= grid_start,
                    BillingOccurrence.billing_date <= grid_end,
                )
                .options(selectinload(BillingOccurrence.service)
                         .selectinload(RecurringService.engagement)
                         .selectinload(Engagement.client))
            )
            invoice_query = select(Invoice).where(
                Invoice.due_date >= grid_start, Invoice.due_date <= grid_end
            ).options(selectinload(Invoice.client), selectinload(Invoice.engagement))
            project_query = select(Project).join(Project.engagement).where(
                Project.due_date >= grid_start, Project.due_date <= grid_end
            ).options(selectinload(Project.engagement).selectinload(Engagement.client))

            if client_id:
                instalment_query = instalment_query.where(Engagement.client_id == client_id)
                occurrence_query = occurrence_query.where(Engagement.client_id == client_id)
                invoice_query = invoice_query.where(Invoice.client_id == client_id)
                project_query = project_query.where(Engagement.client_id == client_id)
            if engagement_id:
                instalment_query = instalment_query.where(Engagement.id == engagement_id)
                occurrence_query = occurrence_query.where(Engagement.id == engagement_id)
                invoice_query = invoice_query.where(Invoice.engagement_id == engagement_id)
                project_query = project_query.where(Project.engagement_id == engagement_id)
            if project_id:
                project = session.get(Project, project_id)
                if project:
                    instalment_query = instalment_query.where(Engagement.id == project.engagement_id)
                    occurrence_query = occurrence_query.where(Engagement.id == project.engagement_id)
                    invoice_query = invoice_query.where(Invoice.engagement_id == project.engagement_id)
                    project_query = project_query.where(Project.id == project_id)

            for item in session.scalars(instalment_query):
                engagement = item.agreement.engagement
                events.append({
                    "date": item.due_date, "kind": "Instalment", "tone": "amber",
                    "title": item.name, "client": engagement.client.display_name,
                    "engagement": engagement.name,
                    "meta": f"{item.currency} {item.amount:,.2f} · {item.status}",
                    "url": f"/Engagements/{engagement.id}",
                })
            for item in session.scalars(occurrence_query):
                engagement = item.service.engagement
                events.append({
                    "date": item.billing_date, "kind": "Recurring", "tone": "blue",
                    "title": item.service.name, "client": engagement.client.display_name,
                    "engagement": engagement.name,
                    "meta": f"{item.currency} {item.amount:,.2f} · {item.status}",
                    "url": f"/Engagements/{engagement.id}",
                })
            for item in session.scalars(invoice_query):
                events.append({
                    "date": item.due_date, "kind": "Invoice", "tone": "coral",
                    "title": item.invoice_number, "client": item.client.display_name,
                    "engagement": item.engagement.name,
                    "meta": f"{item.currency} {item.outstanding:,.2f} outstanding · {item.status}",
                    "url": f"/Finance/Invoices/{item.id}",
                })
            for item in session.scalars(project_query):
                events.append({
                    "date": item.due_date, "kind": "Project", "tone": "green",
                    "title": item.name, "client": item.engagement.client.display_name,
                    "engagement": item.engagement.name,
                    "meta": f"{item.progress}% complete · {item.status}",
                    "url": f"/Projects/{item.id}",
                })

        events.sort(key=lambda event: (event["date"], event["kind"], event["title"]))
        events_by_date: dict[date, list[dict]] = {}
        for event in events:
            events_by_date.setdefault(event["date"], []).append(event)
        calendar_weeks = [
            [{"date": day, "events": events_by_date.get(day, []),
              "in_month": day.month == selected.month, "is_today": day == today_toronto()}
             for day in week]
            for week in weeks
        ]
        clients = ClientService().list()
        engagements = EngagementService().list()
        projects = ProjectService().list()
        query_suffix = "".join(
            f"&{key}={value}" for key, value in {
                "client_id": client_id, "engagement_id": engagement_id,
                "project_id": project_id, "view": view,
            }.items() if value
        )
        return Template("Calendar/Index.html", context={
            **page_context(request, "Calendar", "calendar", "Client delivery and billing"),
            "calendar_weeks": calendar_weeks, "events": events,
            "selected_month": selected, "previous_month": _shift_month(selected, -1),
            "next_month": _shift_month(selected, 1), "today": today_toronto(),
            "clients": clients, "engagements": engagements, "projects": projects,
            "selected_client": client_id, "selected_engagement": engagement_id,
            "selected_project": project_id, "calendar_view": view,
            "query_suffix": query_suffix,
        })
