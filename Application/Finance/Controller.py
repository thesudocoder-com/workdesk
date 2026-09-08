from datetime import datetime, timedelta

from litestar import Controller, Request, get, post
from litestar.params import FromPath, FromQuery
from litestar.response import Redirect, Response, Template
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from Application.Authentication.Guards import outreach_or_developer
from Application.Authentication.Security import valid_csrf_token
from Application.Common.Enums import (
    AgreementStatus, BillingFrequency, BillingTiming, ExpenseCategory, InvoiceStatus,
    MilestoneStatus, PaymentMethod, RecurringStatus,
)
from Application.Common.Forms import clean_form, form_errors
from Application.Common.Money import format_currency
from Application.Common.Time import business_timezone, today_toronto
from Application.Common.Views import form_context, page_context, redirect_after
from Application.Settings.Service import get_workspace
from Application.Engagements.Service import EngagementService
from Application.Projects.Service import ProjectService
from .Schemas import (
    AgreementCreate, ExpenseCreate, InstalmentCreate, InvoiceCreate, MilestoneCreate,
    PaymentCreate, RecurringServiceCreate, RecurringServiceUpdate,
)
from .Service import FinanceService
from .Pdf import build_invoice_pdf


def invoice_fields() -> list[dict]:
    engagements = EngagementService().list(status="Active")
    currency = get_workspace().currency
    return [
        {"name": "engagement_id", "label": "Engagement", "type": "select", "options": [(e.id, f"{e.client.display_name} — {e.name}") for e in engagements], "required": True, "wide": True},
        {"name": "issue_date", "label": "Issue date", "type": "date", "required": True},
        {"name": "due_date", "label": "Due date", "type": "date", "required": True},
        {"name": "subtotal", "label": f"Subtotal ({currency})", "type": "number", "step": "0.01", "required": True},
        {"name": "tax_amount", "label": f"Tax amount ({currency})", "type": "number", "step": "0.01", "required": True},
        {"name": "notes", "label": "Invoice notes", "type": "textarea", "required": False, "wide": True},
    ]


def payment_fields() -> list[dict]:
    workspace = get_workspace()
    invoices = [x for x in FinanceService().overview()["invoices"] if x.outstanding > 0 and x.status not in {InvoiceStatus.DRAFT.value, InvoiceStatus.CANCELLED.value, InvoiceStatus.PAID.value}]
    return [
        {"name": "invoice_id", "label": "Invoice", "type": "select", "options": [(x.id, f"{x.invoice_number} — {x.client.display_name} — {format_currency(x.outstanding, x.currency)}") for x in invoices], "required": True, "wide": True},
        {"name": "amount", "label": f"Amount received ({workspace.currency})", "type": "number", "step": "0.01", "required": True},
        {"name": "paid_at", "label": f"Received at ({workspace.timezone})", "type": "datetime-local", "required": True},
        {"name": "payment_method", "label": "Payment method", "type": "select", "options": [x.value for x in PaymentMethod], "required": True},
        {"name": "reference", "label": "Reference", "type": "text", "required": False},
        {"name": "notes", "label": "Notes", "type": "textarea", "required": False, "wide": True},
    ]


def expense_fields() -> list[dict]:
    currency = get_workspace().currency
    engagements = EngagementService().list()
    projects = ProjectService().list()
    return [
        {"name": "vendor", "label": "Vendor", "type": "text", "required": True},
        {"name": "description", "label": "Description", "type": "text", "required": True},
        {"name": "amount", "label": f"Amount ({currency})", "type": "number", "step": "0.01", "required": True},
        {"name": "expense_date", "label": "Expense date", "type": "date", "required": True},
        {"name": "category", "label": "Category", "type": "select", "options": [x.value for x in ExpenseCategory], "required": True},
        {"name": "engagement_id", "label": "Engagement (optional)", "type": "select", "options": [(e.id, e.name) for e in engagements], "required": False},
        {"name": "project_id", "label": "Project (optional)", "type": "select", "options": [(p.id, p.name) for p in projects], "required": False},
    ]


def form_template(request: Request) -> str:
    return "Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html"


def recurring_edit_fields(currency: str) -> list[dict]:
    return [
        {"name":"name","label":"Service name","type":"text","required":True,"wide":True},
        {"name":"description","label":"Description","type":"textarea","required":False,"wide":True},
        {"name":"amount","label":f"Amount ({currency})","type":"number","step":"0.01","required":True},
        {"name":"end_date","label":"End date","type":"date","required":False},
        {"name":"tax_rate","label":"Tax rate (%)","type":"number","step":"0.01","required":False},
        {"name":"billing_timing","label":"Billing timing","type":"select","options":[x.value for x in BillingTiming],"required":True},
    ]


class FinanceController(Controller):
    path="/Finance"
    guards=[outreach_or_developer]

    @get()
    async def index(self,request:Request,status:FromQuery[str]="")->Template:
        return Template("Finance/Index.html",context={**page_context(request,"Finance","finance","Cash flow"),**FinanceService().overview(status),"selected_status":status,"statuses":list(InvoiceStatus)})

    @get("/Agreements/New")
    async def new_agreement(self, request: Request, engagement_id: FromQuery[int|None] = None) -> Template:
        engagements = EngagementService().list(status="Active")
        fields = [
            {"name":"engagement_id","label":"Engagement","type":"select","options":[(e.id,f"{e.client.display_name} — {e.name}") for e in engagements],"required":True,"wide":True},
            {"name":"name","label":"Agreement name","type":"text","required":True},
            {"name":"contract_value","label":f"Contract value ({get_workspace().currency})","type":"number","step":"0.01","required":True},
            {"name":"adjustment_amount","label":"Adjustment amount","type":"number","step":"0.01","required":False},
            {"name":"adjustment_reason","label":"Adjustment reason","type":"text","required":False,"wide":True},
            {"name":"status","label":"Status","type":"select","options":[x.value for x in AgreementStatus],"required":True},
        ]
        return Template(form_template(request), context=form_context(request,title="New fixed-fee agreement",subtitle="Contract value and instalments remain traceable separately.",section="finance",action="/Finance/Agreements",cancel_url=f"/Engagements/{engagement_id}" if engagement_id else "/Finance",fields=fields,values={"engagement_id":engagement_id or "","adjustment_amount":"0.00","status":AgreementStatus.ACTIVE.value}))

    @post("/Agreements")
    async def create_agreement(self, request: Request) -> Template | Redirect:
        form=await request.form(); values=dict(form); errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")): errors["form"]="This form expired."
        try: data=AgreementCreate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data=None
        if not errors:
            try: item=FinanceService().create_agreement(data,request.user.id)
            except (ValueError,IntegrityError) as exc: errors["form"]=str(exc) if isinstance(exc,ValueError) else "The agreement could not be saved."
        if errors:
            request.session["error"]="Please correct the agreement details."
            return Redirect(f"/Finance/Agreements/New?engagement_id={values.get('engagement_id','')}",status_code=303)
        request.session["flash"]="Fixed-fee agreement added."
        return redirect_after(request,f"/Engagements/{item.engagement_id}")

    @get("/Instalments/New")
    async def new_instalment(self, request: Request, agreement_id: FromQuery[int]) -> Template:
        fields=[{"name":"agreement_id","label":"Agreement","type":"number","required":True},{"name":"name","label":"Instalment name","type":"text","required":True},{"name":"amount","label":f"Amount ({get_workspace().currency})","type":"number","step":"0.01","required":True},{"name":"due_date","label":"Due date","type":"date","required":False},{"name":"sequence","label":"Sequence","type":"number","required":False}]
        return Template(form_template(request),context=form_context(request,title="New instalment",subtitle="The scheduled total cannot exceed the agreement value.",section="finance",action="/Finance/Instalments",cancel_url="/Finance",fields=fields,values={"agreement_id":agreement_id,"sequence":0}))

    @post("/Instalments")
    async def create_instalment(self, request: Request) -> Redirect:
        form=await request.form()
        if not valid_csrf_token(request.session,form.get("csrf_token")):
            request.session["error"]="This form expired."; return Redirect("/Finance",status_code=303)
        try:
            item=FinanceService().add_instalment(InstalmentCreate.model_validate(clean_form(form)),request.user.id)
        except (ValidationError,ValueError,IntegrityError) as exc:
            request.session["error"]=str(exc); return Redirect("/Finance",status_code=303)
        request.session["flash"]="Instalment added."
        return Redirect(f"/Engagements/{item.agreement.engagement_id}",status_code=303)

    @get("/Recurring/New")
    async def new_recurring(self, request: Request, engagement_id: FromQuery[int|None] = None) -> Template:
        engagements=EngagementService().list(status="Active")
        fields=[{"name":"engagement_id","label":"Engagement","type":"select","options":[(e.id,f"{e.client.display_name} — {e.name}") for e in engagements],"required":True,"wide":True},{"name":"name","label":"Service name","type":"text","required":True},{"name":"description","label":"Description","type":"textarea","required":False,"wide":True},{"name":"amount","label":f"Amount ({get_workspace().currency})","type":"number","step":"0.01","required":True},{"name":"frequency","label":"Frequency","type":"select","options":[x.value for x in BillingFrequency if x != BillingFrequency.ONE_TIME],"required":True},{"name":"interval","label":"Billing interval","type":"number","required":True},{"name":"start_date","label":"Start date","type":"date","required":True},{"name":"end_date","label":"End date","type":"date","required":False},{"name":"tax_rate","label":"Tax rate (%)","type":"number","step":"0.01","required":False},{"name":"billing_timing","label":"Billing timing","type":"select","options":[x.value for x in BillingTiming],"required":True},{"name":"status","label":"Status","type":"select","options":[x.value for x in RecurringStatus],"required":True}]
        values={"engagement_id":engagement_id or "","interval":1,"start_date":today_toronto().isoformat(),"tax_rate":"0.00","billing_timing":BillingTiming.ADVANCE.value,"status":RecurringStatus.ACTIVE.value}
        return Template(form_template(request),context=form_context(request,title="New recurring service",subtitle="Future occurrences are forecast, never current debt.",section="finance",action="/Finance/Recurring",cancel_url=f"/Engagements/{engagement_id}" if engagement_id else "/Finance",fields=fields,values=values))

    @post("/Recurring")
    async def create_recurring(self, request: Request) -> Redirect:
        form=await request.form()
        if not valid_csrf_token(request.session,form.get("csrf_token")):
            request.session["error"]="This form expired."; return Redirect("/Finance",status_code=303)
        try:
            item=FinanceService().create_recurring_service(RecurringServiceCreate.model_validate(clean_form(form)),request.user.id)
        except (ValidationError,ValueError,IntegrityError) as exc:
            request.session["error"]=str(exc); return Redirect("/Finance",status_code=303)
        request.session["flash"]="Recurring service added."
        return Redirect(f"/Engagements/{item.engagement_id}",status_code=303)

    @get("/Recurring/{service_id:int}")
    async def recurring_detail(self, request: Request, service_id: FromPath[int]) -> Template | Redirect:
        item = FinanceService().get_recurring_service(service_id)
        if not item:
            request.session["error"] = "Recurring service not found."
            return Redirect("/Finance", status_code=303)
        return Template("Finance/Recurring.html", context={
            **page_context(request, item.name, "finance", "Recurring service"), "service": item,
        })

    @get("/Recurring/{service_id:int}/Edit")
    async def edit_recurring(self, request: Request, service_id: FromPath[int]) -> Template | Redirect:
        item = FinanceService().get_recurring_service(service_id)
        if not item:
            return Redirect("/Finance", status_code=303)
        fields = recurring_edit_fields(item.currency)
        values = {field["name"]: getattr(item, field["name"], "") or "" for field in fields}
        return Template(form_template(request), context=form_context(
            request, title="Edit recurring service",
            subtitle="Update the fee or service details without rewriting its billing history.",
            section="finance", action=f"/Finance/Recurring/{item.id}/Edit",
            cancel_url=f"/Finance/Recurring/{item.id}", fields=fields, values=values,
        ))

    @post("/Recurring/{service_id:int}/Edit")
    async def update_recurring(self, request: Request, service_id: FromPath[int]) -> Template | Redirect:
        form = await request.form(); values = dict(form); errors = {}
        item = FinanceService().get_recurring_service(service_id)
        if not item:
            return Redirect("/Finance", status_code=303)
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            errors["form"] = "This form expired."
        try: data = RecurringServiceUpdate.model_validate(clean_form(form))
        except ValidationError as exc: errors.update(form_errors(exc)); data = None
        if not errors:
            try: FinanceService().update_recurring_service(service_id, data, request.user.id)
            except (ValueError, IntegrityError) as exc:
                errors["form"] = str(exc) if isinstance(exc, ValueError) else "The service changed. Refresh and try again."
        if errors:
            return Template(form_template(request), context=form_context(
                request, title="Edit recurring service", subtitle="Correct the highlighted fields.",
                section="finance", action=f"/Finance/Recurring/{service_id}/Edit",
                cancel_url=f"/Finance/Recurring/{service_id}",
                fields=recurring_edit_fields(item.currency), values=values, errors=errors,
            ), status_code=422)
        request.session["flash"] = "Recurring service updated."
        return redirect_after(request, f"/Finance/Recurring/{service_id}")

    @post("/Recurring/{service_id:int}/Status/{action:str}")
    async def recurring_status(
        self, request: Request, service_id: FromPath[int], action: FromPath[str]
    ) -> Redirect:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired."
            return Redirect(f"/Finance/Recurring/{service_id}", status_code=303)
        statuses = {
            "pause": RecurringStatus.PAUSED,
            "resume": RecurringStatus.ACTIVE,
            "cancel": RecurringStatus.CANCELLED,
        }
        try:
            status = statuses[action]
            FinanceService().set_recurring_status(service_id, status, request.user.id)
            request.session["flash"] = f"Recurring service {status.value.lower()}."
        except KeyError:
            request.session["error"] = "Unknown recurring service action."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return Redirect(f"/Finance/Recurring/{service_id}", status_code=303)

    @get("/Milestones/New")
    async def new_milestone(self, request: Request, engagement_id: FromQuery[int|None] = None) -> Template:
        engagements = EngagementService().list(status="Active")
        fields = [{"name":"engagement_id","label":"Engagement","type":"select","options":[(e.id,f"{e.client.display_name} — {e.name}") for e in engagements],"required":True,"wide":True},{"name":"name","label":"Milestone name","type":"text","required":True,"placeholder":"Development complete"},{"name":"amount","label":f"Amount ({get_workspace().currency})","type":"number","step":"0.01","required":True},{"name":"due_date","label":"Due date","type":"date","required":False},{"name":"status","label":"Status","type":"select","options":[MilestoneStatus.UPCOMING.value,MilestoneStatus.DUE.value],"required":True}]
        context = form_context(request,title="New payment milestone",subtitle="Capture the agreed instalment before issuing an invoice.",section="finance",action="/Finance/Milestones",cancel_url=f"/Engagements/{engagement_id}" if engagement_id else "/Finance",fields=fields,values={"engagement_id":engagement_id or "","status":MilestoneStatus.UPCOMING.value},prerequisite=None if engagements else {"title":"Create an active engagement first","message":"Payment milestones belong to active engagements.","url":"/Projects/New","action":"Start guided setup"})
        return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=context)

    @post("/Milestones")
    async def create_milestone(self, request: Request) -> Template | Redirect:
        form=await request.form();values=dict(form);errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")):errors["form"]="This form expired."
        try:data=MilestoneCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if errors:
            engagements=EngagementService().list(status="Active");fields=[{"name":"engagement_id","label":"Engagement","type":"select","options":[(e.id,e.name) for e in engagements],"required":True},{"name":"name","label":"Milestone name","type":"text","required":True},{"name":"amount","label":f"Amount ({get_workspace().currency})","type":"number","step":"0.01","required":True},{"name":"due_date","label":"Due date","type":"date","required":False},{"name":"status","label":"Status","type":"select","options":[MilestoneStatus.UPCOMING.value,MilestoneStatus.DUE.value],"required":True}]
            return Template("Common/_Form.html" if request.headers.get("HX-Request") else "Common/Form.html",context=form_context(request,title="New payment milestone",subtitle="Correct the highlighted fields.",section="finance",action="/Finance/Milestones",cancel_url="/Finance",fields=fields,values=values,errors=errors),status_code=422)
        try: item=FinanceService().create_milestone(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            engagements=EngagementService().list(status="Active");fields=[{"name":"engagement_id","label":"Engagement","type":"select","options":[(e.id,e.name) for e in engagements],"required":True},{"name":"name","label":"Milestone name","type":"text","required":True},{"name":"amount","label":"Amount","type":"number","step":"0.01","required":True},{"name":"due_date","label":"Due date","type":"date","required":False},{"name":"status","label":"Status","type":"select","options":[x.value for x in MilestoneStatus],"required":True}]
            return Template(form_template(request),context=form_context(request,title="New payment milestone",subtitle="Correct the highlighted fields.",section="finance",action="/Finance/Milestones",cancel_url="/Finance",fields=fields,values=values,errors=errors),status_code=422)
        request.session["flash"]="Payment milestone added."
        return redirect_after(request,f"/Engagements/{item.engagement_id}")

    @get("/Invoices/New")
    async def new_invoice(self,request:Request,engagement_id:FromQuery[int|None]=None)->Template:
        today = today_toronto()
        workspace = get_workspace()
        engagements = EngagementService().list(status="Active")
        context=form_context(request,title="New invoice",subtitle=f"Issue an invoice in {workspace.currency}. Tax remains flexible.",section="finance",action="/Finance/Invoices",cancel_url=f"/Engagements/{engagement_id}" if engagement_id else "/Finance",fields=invoice_fields(),values={"engagement_id":engagement_id or "","issue_date":today.isoformat(),"due_date":(today + timedelta(days=workspace.payment_terms_days)).isoformat(),"tax_amount":"0.00","status":InvoiceStatus.SENT.value},prerequisite=None if engagements else {"title":"Create an active engagement first","message":"Invoices must be tied to active client work.","url":"/Projects/New","action":"Start guided setup"})
        return Template(form_template(request),context=context)

    @post("/Invoices")
    async def create_invoice(self,request:Request)->Template|Redirect:
        form=await request.form();values=dict(form);errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")):errors["form"]="This form expired."
        try:data=InvoiceCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if errors:
            return Template(form_template(request),context=form_context(request,title="New invoice",subtitle="Please correct the highlighted fields.",section="finance",action="/Finance/Invoices",cancel_url="/Finance",fields=invoice_fields(),values=values,errors=errors),status_code=422)
        try: FinanceService().create_invoice(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            return Template(form_template(request),context=form_context(request,title="New invoice",subtitle="Please correct the highlighted fields.",section="finance",action="/Finance/Invoices",cancel_url="/Finance",fields=invoice_fields(),values=values,errors=errors),status_code=422)
        request.session["flash"]="Invoice created."
        return redirect_after(request,"/Finance")

    @post("/Invoices/{invoice_id:int}/Delete")
    async def delete_invoice(self, request: Request, invoice_id: FromPath[int]) -> Redirect | Response:
        form = await request.form()
        if not valid_csrf_token(request.session, form.get("csrf_token")):
            request.session["error"] = "This form expired. Please refresh and try again."
            return redirect_after(request, "/Finance")
        try:
            FinanceService().delete_invoice(invoice_id, request.user.id)
            request.session["flash"] = "Invoice deleted."
        except ValueError as exc:
            request.session["error"] = str(exc)
        return redirect_after(request, "/Finance")

    @get("/Invoices/{invoice_id:int}")
    async def invoice_detail(self, request: Request, invoice_id: FromPath[int]) -> Template | Redirect:
        invoice = FinanceService().get_invoice(invoice_id)
        if not invoice:
            request.session["error"] = "Invoice not found."
            return Redirect("/Finance", status_code=303)
        workspace = get_workspace()
        business = {"name": workspace.legal_name or workspace.business_name,"display_name":workspace.business_name,"email":workspace.business_email,"phone":workspace.business_phone,"address":", ".join(value for value in [workspace.address_line1,workspace.city,workspace.region,workspace.postal_code,workspace.country] if value),"tax_number":workspace.tax_information,"footer":workspace.invoice_footer}
        return Template("Finance/Invoice.html", context={**page_context(request, invoice.invoice_number, "finance", "Invoice"), "invoice": invoice, "business": business})

    @get("/Invoices/{invoice_id:int}/Download")
    async def download_invoice(self, request: Request, invoice_id: FromPath[int]) -> Response | Redirect:
        invoice = FinanceService().get_invoice(invoice_id)
        if not invoice:
            request.session["error"] = "Invoice not found."
            return Redirect("/Finance", status_code=303)
        workspace = get_workspace()
        document = build_invoice_pdf(invoice, workspace)
        safe_number = "".join(character for character in invoice.invoice_number if character.isalnum() or character in {"-", "_"})
        return Response(
            content=document,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_number or "invoice"}.pdf"',
                "Cache-Control": "private, no-store",
            },
        )

    @get("/Payments/New")
    async def new_payment(self,request:Request,invoice_id:FromQuery[int|None]=None)->Template:
        values={"invoice_id":invoice_id or "","paid_at":datetime.now(business_timezone()).strftime("%Y-%m-%dT%H:%M"),"payment_method":PaymentMethod.ETRANSFER.value}
        outstanding = [x for x in FinanceService().overview()["invoices"] if x.outstanding > 0 and x.status not in {InvoiceStatus.DRAFT.value,InvoiceStatus.CANCELLED.value,InvoiceStatus.PAID.value}]
        return Template(form_template(request),context=form_context(request,title="Record payment",subtitle="Record actual funds received against an invoice.",section="finance",action="/Finance/Payments",cancel_url="/Finance",fields=payment_fields(),values=values,prerequisite=None if outstanding else {"title":"No outstanding invoices","message":"Send an invoice before recording a payment.","url":"/Finance/Invoices/New","action":"Create invoice"}))

    @post("/Payments")
    async def payment(self,request:Request)->Template|Redirect:
        form=await request.form();values=dict(form);errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")):errors["form"]="This form expired."
        try:data=PaymentCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if not errors:
            try:FinanceService().record_payment(data,request.user.id)
            except (ValueError, IntegrityError) as exc:errors["form"]=str(exc) if isinstance(exc,ValueError) else "The invoice changed. Refresh and try again."
        if errors:
            return Template(form_template(request),context=form_context(request,title="Record payment",subtitle="Please correct the payment details.",section="finance",action="/Finance/Payments",cancel_url="/Finance",fields=payment_fields(),values=values,errors=errors),status_code=422)
        request.session["flash"]="Payment recorded and invoice balance updated."
        return redirect_after(request,"/Finance")

    @get("/Expenses/New")
    async def new_expense(self,request:Request)->Template:
        return Template(form_template(request),context=form_context(request,title="Add expense",subtitle=f"Record a project or engagement cost in {get_workspace().currency}.",section="finance",action="/Finance/Expenses",cancel_url="/Finance",fields=expense_fields(),values={"expense_date":today_toronto().isoformat(),"category":ExpenseCategory.OTHER.value}))

    @post("/Expenses")
    async def expense(self,request:Request)->Template|Redirect:
        form=await request.form();values=dict(form);errors={}
        if not valid_csrf_token(request.session,form.get("csrf_token")):errors["form"]="This form expired."
        try:data=ExpenseCreate.model_validate(clean_form(form))
        except ValidationError as exc:errors.update(form_errors(exc));data=None
        if errors:
            return Template(form_template(request),context=form_context(request,title="Add expense",subtitle="Please correct the expense details.",section="finance",action="/Finance/Expenses",cancel_url="/Finance",fields=expense_fields(),values=values,errors=errors),status_code=422)
        try: FinanceService().add_expense(data,request.user.id)
        except (ValueError, IntegrityError) as exc:
            errors["form"] = str(exc) if isinstance(exc, ValueError) else "A selected record changed. Refresh and try again."
            return Template(form_template(request),context=form_context(request,title="Add expense",subtitle="Please correct the expense details.",section="finance",action="/Finance/Expenses",cancel_url="/Finance",fields=expense_fields(),values=values,errors=errors),status_code=422)
        request.session["flash"]="Expense recorded."
        return redirect_after(request,"/Finance")
