from enum import StrEnum


class ClientStatus(StrEnum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    ARCHIVED = "Archived"


class EngagementStatus(StrEnum):
    DRAFT = "Draft"
    ACTIVE = "Active"
    ON_HOLD = "On Hold"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class EngagementType(StrEnum):
    WEBSITE = "Website Development"
    SOFTWARE = "Custom Software"
    RETAINER = "Retainer"
    MARKETING = "Marketing"
    CONSULTING = "Consulting"
    MAINTENANCE = "Maintenance"
    OTHER = "Other"


class BillingFrequency(StrEnum):
    ONE_TIME = "One Time"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    ANNUAL = "Annual"
    CUSTOM = "Custom"


class ProjectStatus(StrEnum):
    PLANNING = "Planning"
    ACTIVE = "Active"
    ON_HOLD = "On Hold"
    REVIEW = "Review"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class TaskStatus(StrEnum):
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    REVIEW = "Review"
    DONE = "Done"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"


class MilestoneStatus(StrEnum):
    UPCOMING = "Upcoming"
    DUE = "Due"
    INVOICED = "Invoiced"
    PAID = "Paid"


class InvoiceStatus(StrEnum):
    DRAFT = "Draft"
    SENT = "Sent"
    PARTIALLY_PAID = "Partially Paid"
    PAID = "Paid"
    OVERDUE = "Overdue"
    CANCELLED = "Cancelled"


class PaymentMethod(StrEnum):
    ETRANSFER = "Interac E-Transfer"
    BANK = "Bank Transfer"
    CARD = "Credit Card"
    CHEQUE = "Cheque"
    CASH = "Cash"
    OTHER = "Other"


class ExpenseCategory(StrEnum):
    HOSTING = "Hosting"
    DOMAINS = "Domains"
    SOFTWARE = "Software"
    ADVERTISING = "Advertising"
    CONTRACTORS = "Contractors"
    ASSETS = "Design Assets"
    TRAVEL = "Travel"
    OTHER = "Other"
