from .routes import user

def import_routes(app):
    app.register_blueprint(user)