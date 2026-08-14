"""Flask application factory and development entry point."""

from __future__ import annotations

from flask import Flask

from config import AppConfig, load_session_secret
from controllers import register_controllers
from services import init_services


def create_app(config: dict | object | None = None) -> Flask:
    """Build an isolated application instance.

    ``config`` accepts a mapping for tests or a Flask configuration object for
    alternate deployments.
    """

    app = Flask(__name__)
    app.config.from_object(AppConfig)
    if config:
        if isinstance(config, dict):
            app.config.update(config)
        else:
            app.config.from_object(config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_session_secret()

    init_services(app)
    register_controllers(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
