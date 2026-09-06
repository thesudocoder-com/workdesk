from collections import defaultdict
from decimal import Decimal

from Application.Finance.Service import FinanceService
from Application.Projects.Service import ProjectService


class ReportsService:
    def get(self) -> dict:
        finance = FinanceService().overview()
        revenue_by_client: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        expense_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for payment in finance["payments"]:
            if not payment.is_void:
                revenue_by_client[payment.invoice.client.display_name] += payment.amount
        for expense in finance["expenses"]:
            expense_by_category[expense.category] += expense.amount
        projects = ProjectService().list()
        revenue = sorted(revenue_by_client.items(), key=lambda item: item[1], reverse=True)
        expenses = sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)

        def ranked_rows(items: list[tuple[str, Decimal]]) -> list[dict]:
            largest = items[0][1] if items else Decimal("0")
            return [
                {
                    "name": name,
                    "value": value,
                    "percent": int((value / largest) * 100) if largest else 0,
                }
                for name, value in items
            ]

        valid_invoices = [item for item in finance["invoices"] if item.status != "Cancelled"]
        return {
            **finance,
            "projects": projects,
            "active_projects": sum(item.status == "Active" for item in projects),
            "total_billed": sum((item.total for item in valid_invoices), Decimal("0")),
            "total_collected": sum(
                (payment.amount for payment in finance["payments"] if not payment.is_void),
                Decimal("0"),
            ),
            "total_expenses": sum((expense.amount for expense in finance["expenses"]), Decimal("0")),
            "revenue_by_client": ranked_rows(revenue),
            "expense_by_category": ranked_rows(expenses),
        }
