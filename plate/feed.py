from datetime import datetime

from flask import Blueprint, render_template

from plate.articles import retrieve_articles

bp = Blueprint('feed', __name__)


@bp.route('/')
def get_feed():
    articles = retrieve_articles('all', 32)
    for article in articles:
        published = datetime.fromtimestamp(article['published'])
        article['published'] = published.strftime('%d.%m.%Y %H:%M')
        summary = article['summary']
        max_length = 500
        if len(summary) > max_length:
            article['summary'] = summary[:max_length] + '...'
    return render_template('base.html', articles=articles)
