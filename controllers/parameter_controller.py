"""Simulation parameter controller."""

from flask import flash, render_template, request

from controllers import dashboard_bp
from models.parameter_model import (
    IGNORED_FIELD_NAMES,
    PRODUCT_LABELS,
    load_parameter_groups,
    save_parameter_values,
)


@dashboard_bp.route("/input-parameter", methods=["GET", "POST"])
def input_parameter():
    parameter_mode = request.values.get("parameter_mode", "developer")
    if parameter_mode not in {"developer", "production"}:
        parameter_mode = "developer"

    selected_product = request.values.get("product", "ckr")
    if selected_product not in PRODUCT_LABELS:
        selected_product = "ckr"

    active_group_key = request.form.get("active_group_key", "0")
    if request.method == "POST":
        updated, skipped = save_parameter_values(
            request.form,
            active_group_key,
            parameter_mode,
            selected_product,
        )
        if updated:
            flash(f"{updated} parameter berhasil disimpan ke file case.", "success")
        else:
            flash(
                "Tidak ada parameter yang berubah. "
                "Cek input atau location yang belum didukung.",
                "warning",
            )
        if skipped:
            flash("Location belum diproses untuk: " + ", ".join(skipped), "warning")

    return render_template(
        "input_parameter.html",
        groups=load_parameter_groups(parameter_mode, selected_product),
        title="Input Parameter",
        IGNORED_FIELD_NAMES=IGNORED_FIELD_NAMES,
        active_group_key=active_group_key,
        parameter_mode=parameter_mode,
        selected_product=selected_product,
        product_labels=PRODUCT_LABELS,
    )

