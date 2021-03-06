from flask import Blueprint, abort

from plate.db import get_db

bp = Blueprint('articles', __name__, url_prefix='/articles')


def parse_sites(sites):
    if sites == 'all':
        return '', ()
    else:
        parts = sites.split(',')
        try:
            parts = [int(part) for part in parts]
        except ValueError:
            abort(400)
        qs = ', '.join(['?' for _ in parts])
        return f's.id IN ({qs}) ', tuple(parts)


def assemble_where(sites_term, sites_values, last_article_published):
    if len(sites_values) == 0 and last_article_published is None:
        return '', ()
    else:
        term = 'WHERE '
        values = ()
        if len(sites_values) > 0:
            term += sites_term
            values += sites_values

        if last_article_published is not None:
            if len(values) > 0:
                term += 'AND '
            term += 'a.published < ? '
            values += (last_article_published,)

        return term, values


def retrieve_articles(sites, n_articles, last_article_published=None):
    sites_term, sites_values = parse_sites(sites)
    where_term, where_values = assemble_where(sites_term, sites_values, last_article_published)

    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT name AS site, title, summary, link, thumbnail, author, published, icon '
                   'FROM article a JOIN site s on s.id = a.site_id '
                   f'{where_term}'
                   'ORDER BY published DESC LIMIT ?', where_values + (n_articles,))
    return [dict(row) for row in cursor.fetchall()]


@bp.route("/<sites>/<int:n_articles>")
@bp.route("/<sites>/<int:n_articles>/<int:last_article_published>")
def request_articles(sites, n_articles, last_article_published=None):
    articles = retrieve_articles(sites, n_articles, last_article_published)
    return {'articles': articles}
