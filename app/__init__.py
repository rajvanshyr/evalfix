import json
from flask import Flask
from .extensions import db, migrate
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Flask-Migrate can detect them
    from .models import project, prompt_file, prompt, prompt_version, test_case, failure, optimization_run, test_run, test_result  # noqa

    from .routes import projects, prompt_files, prompts, prompt_versions, test_cases, failures, optimization_runs, test_runs

    # All JSON API routes live under /api to avoid clashing with the server-rendered UI routes
    app.register_blueprint(projects.bp,          url_prefix="/api/projects")
    app.register_blueprint(prompt_files.bp,      url_prefix="/api")
    app.register_blueprint(prompts.bp,           url_prefix="/api")
    app.register_blueprint(prompt_versions.bp,   url_prefix="/api")
    app.register_blueprint(test_cases.bp,        url_prefix="/api")
    app.register_blueprint(failures.bp,          url_prefix="/api")
    app.register_blueprint(optimization_runs.bp, url_prefix="/api")
    app.register_blueprint(test_runs.bp,         url_prefix="/api")

    from .ui import splash as ui_splash_module, projects as ui_projects_module, prompts as ui_prompts_module
    app.register_blueprint(ui_splash_module.bp)
    app.register_blueprint(ui_projects_module.bp, url_prefix="/dashboard")
    app.register_blueprint(ui_prompts_module.bp)

    app.jinja_env.filters['from_json'] = json.loads

    return app
