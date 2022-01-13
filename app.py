import sqlite3

from flask import Flask

app = Flask(__name__)


@app.route("/articles/<int:n_articles>")
@app.route("/articles/<int:n_articles>/<int:last_article_published>")
def request_articles(n_articles, last_article_published=None):
    db_con = sqlite3.connect('articles.db')
    cursor = db_con.cursor()
    if last_article_published is None:
        cursor.execute('SELECT name, title, summary, thumbnail, author, published '
                       'FROM article a JOIN site s on s.id = a.site_id '
                       'ORDER BY published DESC LIMIT ?', (n_articles,))
        return query_to_dict('articles', cursor.fetchall(),
                             ['site', 'title', 'summary', 'thumbnail', 'author', 'published'])
    else:
        cursor.execute('SELECT name, title, summary, thumbnail, author, published '
                       'FROM article a JOIN site s on s.id = a.site_id '
                       'WHERE a.published < ? '
                       'ORDER BY published DESC LIMIT ?', (last_article_published, n_articles))
        return query_to_dict('articles', cursor.fetchall(),
                             ['site', 'title', 'summary', 'thumbnail', 'author', 'published'])


def query_to_dict(name, query, keys):
    return {name: [{key: value for key, value in zip(keys, result)} for result in query]}
