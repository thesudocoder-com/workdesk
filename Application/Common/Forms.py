from typing import Any

from pydantic import ValidationError


def form_errors(error: ValidationError) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in error.errors():
        field = str(item["loc"][0]) if item.get("loc") else "form"
        result.setdefault(field, str(item["msg"]).replace("Value error, ", ""))
    return result


def clean_form(form: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dict(form).items():
        if isinstance(value, str):
            value = value.strip()
        if value != "":
            result[key] = value
    return result
