import json
import re
from pathlib import Path


PARAMETER_TEMPLATE_PATH = Path(__file__).with_name("parameter_templates.json")
CASE_DIR = Path(__file__).resolve().parents[2] / "sprayDryer-6.0.0-onProduct-Trial02"
IGNORED_FIELD_NAMES = {
    "nozzle_operating_pressure",
    # "rosin_rammler_characteristic_diameter_d",
    "water_activity_correction_a_w",
    "gas_phase_turbulence_model",
}


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
                field.setdefault("default_value", _read_field_value(field) or _default_value(field))

    return groups


def save_parameter_values(form_data, active_group_key):
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


def _default_value(field):
    if field.get("input_type") == "text":
        return ""

    placeholder = (field.get("placeholder") or "").strip()
    match = re.match(r"^[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", placeholder)
    if match:
        return match.group(0)
    return placeholder


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
    keys = parts[1:]
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
