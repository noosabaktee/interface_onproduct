"""HTTP controller registration.

Feature controllers share the ``dashboard`` blueprint to keep all existing
``dashboard.*`` endpoint names stable while avoiding one monolithic module.
"""

from flask import Blueprint, Flask


dashboard_bp = Blueprint("dashboard", __name__)


def register_controllers(app: Flask) -> None:
    from controllers.auth_controller import auth_bp

    # Importing feature modules registers their routes on dashboard_bp.
    from controllers import (  # noqa: F401
        case_file_controller,
        dashboard_controller,
        graph_controller,
        parameter_controller,
        paraview_controller,
        processor_controller,
        report_controller,
        simulation_controller,
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
