import sqlite3

from flask import Flask, abort

app = Flask(__name__)


@app.route("/articles/<sites>/<int:n_articles>")
@app.route("/articles/<sites>/<int:n_articles>/<int:last_article_published>")
def request_articles(sites, n_articles, last_article_published=None):
    sites_term, sites_values = parse_sites(sites)
    where_term, where_values = assemble_where(sites_term, sites_values, last_article_published)

    db_con = sqlite3.connect('articles.db')
    cursor = db_con.cursor()
    cursor.execute('SELECT name, title, summary, thumbnail, author, published '
                   'FROM article a JOIN site s on s.id = a.site_id '
                   f'{where_term}'
                   'ORDER BY published DESC LIMIT ?', where_values + (n_articles,))
    return query_to_dict('articles', cursor.fetchall(),
                         ['site', 'title', 'summary', 'thumbnail', 'author', 'published'])


@app.route("/sites")
def request_sites():
    db_con = sqlite3.connect('articles.db')
    cursor = db_con.cursor()
    cursor.execute('SELECT name, id FROM site')
    return query_to_dict('sites', cursor.fetchall(), ['site', 'id'])


def query_to_dict(name, query, keys):
    return {name: [{key: value for key, value in zip(keys, result)} for result in query]}


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
