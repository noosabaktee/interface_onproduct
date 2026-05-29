import json
import re
import ast
import operator
from pathlib import Path


PARAMETER_TEMPLATE_PATH = Path(__file__).with_name("parameter_templates.json")
PRODUCTION_PARAMETER_PATHS = {
    "ckr": Path(__file__).with_name("parameter_ckr.json"),
    "bmt": Path(__file__).with_name("parameter_bmt.json"),
}
PRODUCTION_CONST_PATHS = {
    "ckr": Path(__file__).with_name("const_ckr.json"),
    "bmt": Path(__file__).with_name("const_bmt.json"),
}
CASE_DIR = Path(__file__).resolve().parents[2] / "sprayDryer-6.0.0-onProduct-Trial02"
IGNORED_FIELD_NAMES = {
    "nozzle_operating_pressure",
    # "rosin_rammler_characteristic_diameter_d",
    "water_activity_correction_a_w",
    "gas_phase_turbulence_model",
}
PRODUCT_LABELS = {
    "ckr": "CKR",
    "bmt": "BMT",
}


def load_parameter_groups(mode="developer", product="ckr"):
    if mode == "production":
        return load_production_parameter_groups(product)

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
                field.setdefault("default_value", _read_field_value(field) or _default_value(field))

    return groups


def load_production_parameter_groups(product="ckr"):
    product = _normalize_product(product)
    parameter_path = PRODUCTION_PARAMETER_PATHS[product]
    if not parameter_path.exists():
        return []

    with parameter_path.open("r", encoding="utf-8") as handle:
        fields = json.load(handle)

    visible_fields = []
    for field in fields:
        field.setdefault("unit", "")
        field.setdefault("placeholder", "")
        field.setdefault("input_type", "text")
        field.setdefault("field_name", _field_key(field.get("name", "parameter")))
        field.setdefault("default_value", _default_value(field))
        if not _is_hidden(field):
            visible_fields.append(field)

    return [
        {
            "key": "production",
            "title": f"Production Parameters - {PRODUCT_LABELS[product]}",
            "sections": [
                {
                    "number": PRODUCT_LABELS[product],
                    "title": "Production Input",
                    "group_key": "production",
                    "fields": visible_fields,
                }
            ],
        }
    ]


def save_parameter_values(form_data, active_group_key, mode="developer", product="ckr"):
    if mode == "production":
        return save_production_parameter_values(form_data, product)

    if active_group_key == "6":
        return 0, ["Tab 6 belum ditulis karena location file-nya belum benar."]

    updated = 0
    skipped = []
    groups = load_parameter_groups()

    for group in groups:
        if str(group.get("key")) != str(active_group_key):
            continue

        for section in group.get("sections", []):
            for field in section.get("fields", []):
                field_name = field.get("field_name")
                if not field_name or field_name not in form_data:
                    continue

                if _should_skip_field(field, group.get("key")):
                    skipped.append(field.get("name", field_name))
                    continue

                value = form_data.get(field_name, "").strip()
                if value == "":
                    continue

                for location in _iter_locations(field.get("location")):
                    if _write_location_value(location, value):
                        updated += 1
                    else:
                        skipped.append(field.get("name", field_name))
    return updated, sorted(set(skipped))


def save_production_parameter_values(form_data, product="ckr"):
    product = _normalize_product(product)
    parameter_path = PRODUCTION_PARAMETER_PATHS[product]
    if not parameter_path.exists():
        return 0, [f"Parameter production {PRODUCT_LABELS[product]} tidak ditemukan."]

    with parameter_path.open("r", encoding="utf-8") as handle:
        fields = json.load(handle)

    constants = _load_product_constants(product)
    context = dict(constants)
    updated = 0
    skipped = []

    for field in fields:
        field_name = field.get("field_name")
        display_name = field.get("name", field_name or "parameter")
        raw_input = _production_input_value(field, form_data, context)

        try:
            calculated = _calculate_production_value(field, raw_input, context)
        except (ValueError, ZeroDivisionError, SyntaxError) as exc:
            skipped.append(f"{display_name} ({exc})")
            continue

        _store_context_aliases(context, field, calculated)

        for location in _iter_locations(field.get("location")):
            if _write_location_value(location, _format_number(calculated)):
                updated += 1
            else:
                skipped.append(display_name)

    return updated, sorted(set(skipped))


def _default_value(field):
    if field.get("input_type") == "text":
        return ""

    placeholder = (field.get("placeholder") or "").strip()
    match = re.match(r"^[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", placeholder)
    if match:
        return match.group(0)
    return placeholder


def _normalize_product(product):
    product = (product or "ckr").lower()
    return product if product in PRODUCTION_PARAMETER_PATHS else "ckr"


def _is_hidden(field):
    hidden = field.get("hidden", False)
    if isinstance(hidden, str):
        return hidden.strip().lower() == "true"
    return bool(hidden)


def _field_key(value):
    value = (value or "parameter").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "parameter"


def _load_product_constants(product):
    const_path = PRODUCTION_CONST_PATHS[product]
    if not const_path.exists():
        return {}

    with const_path.open("r", encoding="utf-8") as handle:
        constants = json.load(handle)

    context = {}
    for item in constants:
        name = item.get("name")
        if not name:
            continue
        try:
            value = _to_number(item.get("nilai"))
        except ValueError:
            continue
        context[name] = value
        context[_field_key(name)] = value
    return context


def _production_input_value(field, form_data, context):
    field_name = field.get("field_name")
    value = form_data.get(field_name, "").strip() if field_name else ""
    if value == "":
        value = str(field.get("placeholder", "")).strip()
    if value == "":
        value = context.get(field_name) or context.get(_field_key(field.get("name")))
    return _to_number(value)


def _calculate_production_value(field, input_value, context):
    formula = (field.get("rumus_logika") or "").strip()
    if not formula:
        return input_value

    expression, variables = _normalize_formula(formula, context)
    variables["input"] = input_value
    variables["Input"] = input_value
    return _safe_eval(expression, variables)


def _normalize_formula(formula, context):
    expression = formula.replace("^", "**")
    expression = re.sub(r"\binput\s*%", "input", expression, flags=re.IGNORECASE)

    variables = {}
    for name, value in sorted(context.items(), key=lambda item: len(str(item[0])), reverse=True):
        if not isinstance(name, str) or not name:
            continue
        safe_name = _field_key(name)
        variables[safe_name] = value
        expression = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", safe_name, expression)
    return expression, variables


def _store_context_aliases(context, field, value):
    aliases = [
        field.get("name"),
        field.get("field_name"),
        _field_key(field.get("name")),
    ]
    for location in _iter_locations(field.get("location")):
        _, keys = _split_location(location)
        if keys:
            aliases.append(keys[-1])

    for alias in aliases:
        if alias:
            context[alias] = value


def _to_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip().replace(",", ".")
    if value == "":
        raise ValueError("input kosong")
    return float(value)


def _format_number(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.12g}"


def _safe_eval(expression, variables):
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"variabel {node.id} tidak ditemukan")
            return variables[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](eval_node(node.operand))
        raise ValueError("rumus tidak didukung")

    tree = ast.parse(expression, mode="eval")
    return eval_node(tree)


def _read_field_value(field):
    if _should_skip_field(field):
        return None

    for location in _iter_locations(field.get("location")):
        value = _read_location_value(location)
        if value is not None:
            return value
    return None


def _should_skip_field(field, group_key=None):
    if str(group_key) == "6":
        return True
    if field.get("field_name") in IGNORED_FIELD_NAMES:
        return True

    locations = list(_iter_locations(field.get("location")))
    if not locations:
        return True

    unsupported_markers = ("indirect", "not yet implemented", "postProcessing", "Lagrangian", "+")
    return any(any(marker in location for marker in unsupported_markers) for location in locations)


def _iter_locations(location):
    if isinstance(location, list):
        yield from (item for item in location if isinstance(item, str))
    elif isinstance(location, str):
        yield location


def _split_location(location):
    parts = [part.strip() for part in location.split(">")]
    if len(parts) < 2:
        return None, []
    file_path = CASE_DIR / parts[0]
    keys = []
    for part in parts[1:]:
        if " " in part and not part.startswith('"'):
            keys.extend(item for item in part.split() if item)
        else:
            keys.append(part)
    if file_path.name == "reactingCloud1Properties" and len(keys) > 2 and keys[0] == "walls":
        keys = keys[1:]
    return file_path, keys


def _read_location_value(location):
    file_path, keys = _split_location(location)
    if not file_path or not file_path.exists() or not keys:
        return None

    text = file_path.read_text(encoding="utf-8", errors="replace")
    block_start, block_end = 0, len(text)
    for key in keys[:-1]:
        block = _find_block(text, key, block_start, block_end)
        if block is None:
            return None
        block_start, block_end = block

    entry = _find_entry(text, keys[-1], block_start, block_end)
    if entry is None:
        return None
    value = text[entry[0]:entry[1]].strip()
    return _display_value(value)


def _write_location_value(location, value):
    file_path, keys = _split_location(location)
    if not file_path or not file_path.exists() or not keys:
        return False

    text = file_path.read_text(encoding="utf-8", errors="replace")
    block_start, block_end = 0, len(text)
    for key in keys[:-1]:
        block = _find_block(text, key, block_start, block_end)
        if block is None:
            return False
        block_start, block_end = block

    replacement = _replace_entry_value(text, keys[-1], value, block_start, block_end)
    if replacement is None:
        return False

    file_path.write_text(replacement, encoding="utf-8")
    return True


def _find_block(text, key, start, end):
    match = None
    for candidate in _key_candidates(key):
        key_pattern = _key_pattern(candidate)
        pattern = re.compile(rf'(?m)^[ \t]*(?:"{key_pattern}"|{key_pattern})\s*\{{|(?<=[\s{{])(?:"{key_pattern}"|{key_pattern})\s*\{{')
        match = pattern.search(text, start, end)
        if match:
            break
    if not match:
        return None

    open_brace = text.find("{", match.start(), match.end())
    close_brace = _matching_brace(text, open_brace)
    if close_brace is None or close_brace > end:
        return None
    return open_brace + 1, close_brace


def _matching_brace(text, open_brace):
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _find_entry(text, key, start, end):
    match = None
    for candidate in _key_candidates(key):
        pattern = _entry_pattern(candidate)
        match = pattern.search(text, start, end)
        if match:
            break
    if not match:
        return None
    return match.start("value"), match.end("value")


def _replace_entry_value(text, key, value, start, end):
    match = None
    for candidate in _key_candidates(key):
        pattern = _entry_pattern(candidate)
        match = pattern.search(text, start, end)
        if match:
            break
    if not match:
        return None

    old_value = match.group("value").strip()
    new_value = _stored_value(old_value, value)
    return text[:match.start("value")] + new_value + text[match.end("value"):]


def _entry_pattern(key):
    key_pattern = _key_pattern(key)
    return re.compile(
        rf'(?P<prefix>(?m:^[ \t]*|(?<=[\s{{]))(?:"{key_pattern}"|{key_pattern})\s+)'
        rf'(?P<value>[^;{{}}]+?)(?P<suffix>\s*;)'
    )


def _key_pattern(key):
    return re.escape(key)


def _key_candidates(key):
    aliases = {
        "obstacle0": "obstacle",
        "d": "lambda",
        "MassTotal": "massTotal",
    }
    yield key
    if key in aliases:
        yield aliases[key]


def _display_value(value):
    value = re.sub(r"\s+", " ", value).strip()
    for qualifier in ("uniform ", "constant "):
        if value.startswith(qualifier):
            return value[len(qualifier):].strip()
    return value


def _stored_value(old_value, new_value):
    old_value = old_value.strip()
    new_value = new_value.strip()
    if old_value.startswith("uniform ") and not _has_openfoam_qualifier(new_value):
        return f"uniform {new_value}"
    if old_value.startswith("constant ") and not _has_openfoam_qualifier(new_value):
        return f"constant {new_value}"
    return new_value


def _has_openfoam_qualifier(value):
    return value.startswith(("uniform ", "constant ", "$"))
