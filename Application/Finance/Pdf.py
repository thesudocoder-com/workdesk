from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from Application.Common.Money import money


FOREST = colors.HexColor("#0D4738")
INK = colors.HexColor("#101B18")
MUTED = colors.HexColor("#53645E")
LINE = colors.HexColor("#D7DFDB")
PALE = colors.HexColor("#F3F6F4")


def _text(value: object | None) -> str:
    return escape(str(value or ""))


def _amount(value: object, currency: str) -> str:
    return f"{currency.upper()} {money(value):,.2f}"


def build_invoice_pdf(invoice, workspace) -> bytes:
    """Build a private, in-memory invoice PDF from the current database record."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=invoice.invoice_number,
        author=workspace.business_name,
        subject=f"Invoice {invoice.invoice_number}",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("InvoiceBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=14, textColor=INK)
    muted = ParagraphStyle("InvoiceMuted", parent=body, fontSize=8.5, textColor=MUTED)
    label = ParagraphStyle("InvoiceLabel", parent=muted, fontName="Helvetica-Bold", fontSize=7.5, leading=10, spaceAfter=3)
    heading = ParagraphStyle("InvoiceHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=FOREST, alignment=TA_RIGHT)
    number = ParagraphStyle("InvoiceNumber", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=TA_RIGHT)
    right = ParagraphStyle("InvoiceRight", parent=body, alignment=TA_RIGHT)

    business_address = ", ".join(
        value for value in [workspace.address_line1, workspace.city, workspace.region, workspace.postal_code, workspace.country] if value
    )
    company_lines = [f"<b>{_text(workspace.business_name)}</b>"]
    if workspace.legal_name and workspace.legal_name != workspace.business_name:
        company_lines.append(_text(workspace.legal_name))
    if business_address:
        company_lines.append(_text(business_address))
    if workspace.business_email:
        company_lines.append(_text(workspace.business_email))
    if workspace.business_phone:
        company_lines.append(_text(workspace.business_phone))

    story = [
        Table(
            [[Paragraph("<br/>".join(company_lines), body), Paragraph("INVOICE", heading)]],
            colWidths=[110 * mm, 64 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
        ),
        Spacer(1, 4 * mm),
        Table(
            [[Paragraph("", body), Paragraph(f"<b>{_text(invoice.invoice_number)}</b><br/><font color='#53645E'>{_text(invoice.status)}</font>", number)]],
            colWidths=[110 * mm, 64 * mm],
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, FOREST), ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
        ),
        Spacer(1, 7 * mm),
    ]

    bill_to = [f"<b>{_text(invoice.client.display_name)}</b>"]
    if invoice.client.name and invoice.client.name != invoice.client.display_name:
        bill_to.append(_text(invoice.client.name))
    if invoice.client.primary_email:
        bill_to.append(_text(invoice.client.primary_email))
    client_address = ", ".join(
        value for value in [invoice.client.address_line1, invoice.client.address_line2, invoice.client.city, invoice.client.province, invoice.client.postal_code, invoice.client.country] if value
    )
    if client_address:
        bill_to.append(_text(client_address))

    story.append(
        Table(
            [[Paragraph("BILL TO", label), Paragraph("INVOICE DETAILS", label)],
             [Paragraph("<br/>".join(bill_to), body), Paragraph(
                 f"Issued: <b>{invoice.issue_date.strftime('%d %b %Y')}</b><br/>Due: <b>{invoice.due_date.strftime('%d %b %Y')}</b><br/>Currency: <b>{_text(invoice.currency)}</b>", right
             )]],
            colWidths=[105 * mm, 69 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]),
        )
    )
    story.append(Spacer(1, 8 * mm))

    amounts = [
        [Paragraph("DESCRIPTION", label), Paragraph("AMOUNT", ParagraphStyle("AmountLabel", parent=label, alignment=TA_RIGHT))],
        [Paragraph(f"<b>Services - {_text(invoice.engagement.name)}</b>", body), Paragraph(_amount(invoice.subtotal, invoice.currency), right)],
        [Paragraph("Tax", body), Paragraph(_amount(invoice.tax_amount, invoice.currency), right)],
        [Paragraph("Total", ParagraphStyle("TotalLabel", parent=body, fontName="Helvetica-Bold")), Paragraph(f"<b>{_amount(invoice.total, invoice.currency)}</b>", right)],
        [Paragraph("Paid", body), Paragraph(_amount(invoice.amount_paid, invoice.currency), right)],
        [Paragraph("Balance due", ParagraphStyle("BalanceLabel", parent=body, fontName="Helvetica-Bold", textColor=FOREST)), Paragraph(f"<b>{_amount(invoice.outstanding, invoice.currency)}</b>", ParagraphStyle("BalanceAmount", parent=right, textColor=FOREST))],
    ]
    amount_table = Table(amounts, colWidths=[119 * mm, 55 * mm], repeatRows=1)
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE), ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E7F1EC")),
    ]))
    story.append(amount_table)

    if invoice.notes:
        story.extend([Spacer(1, 8 * mm), KeepTogether([Paragraph("NOTES", label), Paragraph(_text(invoice.notes).replace("\n", "<br/>"), body)])])
    if workspace.tax_information:
        story.extend([Spacer(1, 5 * mm), KeepTogether([Paragraph("TAX INFORMATION", label), Paragraph(_text(workspace.tax_information).replace("\n", "<br/>"), body)])])
    valid_payments = [payment for payment in invoice.payments if not payment.is_void]
    if valid_payments:
        payment_rows = [[Paragraph("PAYMENT HISTORY", label), Paragraph("AMOUNT", label)]]
        for payment in valid_payments:
            payment_rows.append([
                Paragraph(f"{payment.paid_at.strftime('%d %b %Y')} - {_text(payment.payment_method)}{(' - ' + _text(payment.reference)) if payment.reference else ''}", muted),
                Paragraph(_amount(payment.amount, payment.currency), right),
            ])
        payment_table = Table(payment_rows, colWidths=[119 * mm, 55 * mm], repeatRows=1)
        payment_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.extend([Spacer(1, 8 * mm), payment_table])
    if workspace.invoice_footer:
        story.extend([Spacer(1, 10 * mm), Paragraph(_text(workspace.invoice_footer).replace("\n", "<br/>"), muted)])

    document.build(story)
    return buffer.getvalue()
