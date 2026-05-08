import base64
import io
import re
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


APP_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = APP_ROOT / "report"
GRAPH_OUTPUT_PATH = APP_ROOT / "grafik" / "output"
REPORT_NAME_PATTERN = re.compile(r"^\d{2}_\d{2}_\d{4}$")


def ensure_report_root():
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    return REPORT_ROOT


def today_report_name():
    return datetime.now().strftime("%d_%m_%Y")


def create_report(graph_source=GRAPH_OUTPUT_PATH):
    report_dir = ensure_report_root() / today_report_name()
    report_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = report_dir / "graphs"
    screenshots_dir = report_dir / "screenshots"
    graphs_dir.mkdir(exist_ok=True)
    screenshots_dir.mkdir(exist_ok=True)

    copied = 0
    if graph_source.exists():
        for image_path in sorted(graph_source.glob("*.png"), key=lambda path: path.name.lower()):
            shutil.copy2(image_path, graphs_dir / image_path.name)
            copied += 1

    return get_report(report_dir.name), copied


def latest_report():
    reports = list_reports()
    return reports[0] if reports else None


def list_reports():
    root = ensure_report_root()
    reports = []
    for path in root.iterdir():
        if path.is_dir() and REPORT_NAME_PATTERN.fullmatch(path.name):
            report = get_report(path.name)
            if report:
                reports.append(report)
    return sorted(reports, key=lambda item: item["created_sort"], reverse=True)


def get_report(report_name):
    if not REPORT_NAME_PATTERN.fullmatch(report_name or ""):
        return None

    report_dir = (ensure_report_root() / report_name).resolve()
    if report_dir.parent != REPORT_ROOT.resolve() or not report_dir.is_dir():
        return None

    screenshots = _image_items(report_dir / "screenshots", report_name, "screenshots")
    graphs = _image_items(report_dir / "graphs", report_name, "graphs")
    created = _parse_report_date(report_name)
    created_label = created.strftime("%d %B %Y") if created else report_name.replace("_", "/")

    return {
        "name": report_name,
        "path": report_dir,
        "created_label": created_label,
        "created_sort": created or datetime.fromtimestamp(report_dir.stat().st_mtime),
        "screenshots": screenshots,
        "graphs": graphs,
        "image_count": len(screenshots) + len(graphs),
    }


def delete_report(report_name):
    report = get_report(report_name)
    if not report:
        return False
    shutil.rmtree(report["path"])
    return True


def save_capture(report_name, image_data, side_name):
    report = get_report(report_name) if report_name else latest_report()
    if not report:
        report, _ = create_report()

    safe_side = re.sub(r"[^a-z0-9_-]+", "_", (side_name or "capture").lower()).strip("_")
    safe_side = safe_side or "capture"
    payload = (image_data or "").split(",", 1)[-1]
    try:
        raw = base64.b64decode(payload, validate=True)
        image = Image.open(io.BytesIO(raw))
        image.verify()
    except Exception as exc:
        raise ValueError("Format gambar capture tidak valid.") from exc

    screenshots_dir = report["path"] / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    output_path = screenshots_dir / f"{safe_side}.png"
    output_path.write_bytes(raw)
    return get_report(report["name"]), output_path.name


def build_report_pdf(report_name):
    report = get_report(report_name)
    if not report:
        return None

    pages = []
    title_page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(title_page)
    draw.text((80, 80), "Simulation Report", fill="#111827")
    draw.text((80, 130), report["created_label"], fill="#374151")
    draw.text((80, 180), f"Screenshots: {len(report['screenshots'])}", fill="#374151")
    draw.text((80, 220), f"Graphs: {len(report['graphs'])}", fill="#374151")
    pages.append(title_page)

    for item in report["screenshots"] + report["graphs"]:
        source = report["path"] / item["relative_path"]
        try:
            image = Image.open(source).convert("RGB")
        except OSError:
            continue
        page = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(page)
        draw.text((80, 70), item["title"], fill="#111827")
        fitted = ImageOps.contain(image, (1080, 1500))
        x = (1240 - fitted.width) // 2
        y = 150 + ((1500 - fitted.height) // 2)
        page.paste(fitted, (x, y))
        pages.append(page)

    buffer = io.BytesIO()
    first, rest = pages[0], pages[1:]
    first.save(buffer, format="PDF", save_all=True, append_images=rest)
    buffer.seek(0)
    return buffer


def _image_items(folder, report_name, group):
    if not folder.exists():
        return []

    items = []
    for path in sorted(folder.glob("*.png"), key=lambda item: item.name.lower()):
        items.append(
            {
                "name": path.name,
                "title": path.stem.replace("_", " ").replace("-", " ").title(),
                "relative_path": f"{group}/{path.name}",
                "url_path": f"{report_name}/{group}/{path.name}",
            }
        )
    return items


def _parse_report_date(report_name):
    try:
        return datetime.strptime(report_name, "%d_%m_%Y")
    except ValueError:
        return None
