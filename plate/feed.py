import time
from datetime import datetime

from flask import Blueprint, render_template

from plate.articles import retrieve_articles

bp = Blueprint('feed', __name__)


def format_time_delta(delta):
    """Formats time delta in seconds."""
    spm = 60
    sph = spm * 60
    spd = sph * 24

    seconds = int(delta % spm)
    minutes = int((delta % sph) / spm)
    hours = int((delta % spd) / sph)
    days = int(delta / spd)

    if delta < spm:
        return f'{seconds} second{"s" if seconds != 1 else ""}'
    elif delta < sph:
        return f'{minutes} minute{"s" if minutes != 1 else ""}'
    elif delta < spd:
        return f'{hours} hour{"s" if hours != 1 else ""}, {minutes} minute{"s" if minutes != 1 else ""}'
    else:
        return f'{days} day{"s" if days != 1 else ""}, {hours} hour{"s" if hours != 1 else ""}, ' \
               f'{minutes} minute{"s" if minutes != 1 else ""}'


@bp.route('/')
@bp.route("/<sites>")
@bp.route("/<sites>/<int:n_articles>")
@bp.route("/<sites>/<int:n_articles>/<int:last_article_published>")
def get_feed(sites='all', n_articles=35, last_article_published=None):
    articles = retrieve_articles(sites, n_articles, last_article_published)
    current_time = time.time()

    last = min([article['published'] for article in articles])

    for article in articles:
        pub_time = article['published']
        article['published_since'] = format_time_delta(current_time - pub_time)
        published = datetime.fromtimestamp(article['published'])
        article['published'] = published.strftime('%d.%m.%Y %H:%M (UTC)')
        summary = article['summary']
        max_length = 500
        if len(summary) > max_length:
            article['summary'] = summary[:max_length] + '...'

    return render_template('base.html', articles=articles, sites=sites, n_articles=n_articles, last=last)
