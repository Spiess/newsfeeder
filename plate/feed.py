from flask import Blueprint, render_template

from plate.articles import retrieve_articles

bp = Blueprint('feed', __name__)


@bp.route('/')
def get_feed():
    articles = retrieve_articles('all', 32)
    return render_template('base.html', articles=articles)
