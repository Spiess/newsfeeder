from flask import Blueprint

bp = Blueprint('feed', __name__)


@bp.route('/')
def get_feed():
    return '<p>Hello!</p>'
