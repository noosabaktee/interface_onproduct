import json
import re
from functools import lru_cache
from pathlib import Path


PARAMETER_TEMPLATE_PATH = Path(__file__).with_name("parameter_templates.json")


@lru_cache(maxsize=1)
def load_parameter_groups():
    if not PARAMETER_TEMPLATE_PATH.exists():
        return []

    with PARAMETER_TEMPLATE_PATH.open("r", encoding="utf-8") as handle:
        groups = json.load(handle)

    for group in groups:
        group.setdefault("sections", [])
        for section in group["sections"]:
            section.setdefault("fields", [])
            for field in section["fields"]:
                field.setdefault("unit", "")
                field.setdefault("placeholder", "")
                field.setdefault("input_type", "text")
                field.setdefault("field_name", "parameter")
                field.setdefault("default_value", _default_value(field))

    return groups


def _default_value(field):
    if field.get("input_type") == "text":
        return ""

    placeholder = (field.get("placeholder") or "").strip()
    match = re.match(r"^[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", placeholder)
    if match:
        return match.group(0)
    return placeholder
