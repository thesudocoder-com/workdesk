from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from Application.Activity.Models import Activity
from Application.Common.Enums import InvoiceStatus, ProjectStatus, TaskStatus
from Application.Common.Time import today_toronto
from Application.Finance.Models import Invoice
from Application.Engagements.Models import Engagement
from Application.Projects.Models import Project
from Application.Tasks.Models import WorkTask


def dashboard_data(session, user_id: int, include_finance: bool) -> dict:
    today = today_toronto()
    projects = list(session.scalars(select(Project).where(Project.status.in_([ProjectStatus.ACTIVE.value, ProjectStatus.PLANNING.value, ProjectStatus.REVIEW.value])).options(selectinload(Project.engagement).selectinload(Engagement.client), selectinload(Project.owner)).order_by(Project.due_date).limit(6)))
    invoices = list(session.scalars(select(Invoice).where(Invoice.status != InvoiceStatus.CANCELLED.value).options(selectinload(Invoice.client), selectinload(Invoice.payments)).order_by(Invoice.due_date))) if include_finance else []
    tasks = list(session.scalars(select(WorkTask).where(WorkTask.assigned_to_id == user_id, WorkTask.status != TaskStatus.DONE.value).options(selectinload(WorkTask.project), selectinload(WorkTask.assignee)).order_by(WorkTask.due_date).limit(6)))
    overdue_tasks = list(session.scalars(select(WorkTask).where(WorkTask.due_date < today, WorkTask.status != TaskStatus.DONE.value).options(selectinload(WorkTask.project))))
    activity = list(session.scalars(select(Activity).options(selectinload(Activity.user)).order_by(Activity.created_at.desc()).limit(8)))
    outstanding = sum((item.outstanding for item in invoices), Decimal("0"))
    due_30 = sum((item.outstanding for item in invoices if today <= item.due_date <= today + timedelta(days=30)), Decimal("0"))
    upcoming = [item for item in invoices if item.outstanding > 0 and item.due_date <= today + timedelta(days=30)][:5]
    alerts = []
    for invoice in invoices:
        if invoice.due_date < today and invoice.outstanding > 0:
            alerts.append({"level":"high","title":f"{invoice.invoice_number} is overdue","detail":invoice.client.display_name,"value":invoice.outstanding,"meta":f"{(today-invoice.due_date).days} days overdue","type":"money"})
    for project in projects:
        if project.due_date and project.due_date <= today + timedelta(days=5):
            level = "high" if project.progress < 70 else "medium"
            alerts.append({"level":level,"title":project.name,"detail":project.engagement.client.display_name,"value":project.progress,"meta":f"Due {project.due_date.strftime('%b %d')}","type":"progress"})
    if overdue_tasks:
        alerts.append({"level":"medium","title":f"{len(overdue_tasks)} overdue task{'s' if len(overdue_tasks)!=1 else ''}","detail":"Across active delivery work","value":len(overdue_tasks),"meta":"Review now","type":"count"})
    due_7_tasks = sum(task.due_date is not None and today <= task.due_date <= today + timedelta(days=7) for task in tasks)
    return {"today":today,"projects":projects,"invoices":invoices,"my_tasks":tasks,"upcoming_invoices":upcoming,"activity":activity,"alerts":alerts[:6],"active_projects":len(projects),"outstanding":outstanding,"due_30":due_30,"overdue_tasks":len(overdue_tasks),"due_7_tasks":due_7_tasks,"can_manage_finance":include_finance}
