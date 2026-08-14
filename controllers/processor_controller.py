"""Processor configuration controller."""

from flask import flash, render_template, request

from controllers import dashboard_bp
from services import get_processor_service


@dashboard_bp.route("/set-processor", methods=["GET", "POST"])
def set_processor():
    service = get_processor_service()
    processor_count = service.normalize(service.load())

    if request.method == "POST":
        try:
            processor_count = service.save(request.form.get("processor_count"))
            flash(
                f"Jumlah processor diset ke {processor_count}. "
                "File decomposeParDict diperbarui.",
                "success",
            )
        except OSError:
            flash(
                "Gagal menyimpan jumlah processor ke decomposeParDict. "
                "Pastikan file tersedia dan dapat ditulis.",
                "danger",
            )

    return render_template(
        "set_processor.html",
        processor_count=processor_count,
        max_processor_count=service.maximum_count,
        title="Set Processor",
    )

