from flask import Blueprint, render_template

bp = Blueprint("ui_splash", __name__)


@bp.route("/")
def index():
    return render_template("splash.html")
