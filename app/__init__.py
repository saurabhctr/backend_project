from flask import Flask
from .models import models
from .routes import routes
from .utils import helpers

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    # Register Blueprints
    from .routes.routes import auth_bp
    app.register_blueprint(auth_bp)

    return app
