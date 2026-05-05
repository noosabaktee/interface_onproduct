from flask import Flask

from controllers.dashboard_controller import dashboard_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = "maintenance-chamber-dev"
    app.register_blueprint(dashboard_bp)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
