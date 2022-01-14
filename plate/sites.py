from flask import Blueprint

from plate.db import get_db

bp = Blueprint('sites', __name__, url_prefix='/sites')


@bp.route("/")
def request_sites():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT name AS site, id FROM site')
    return {'sites': [dict(row) for row in cursor.fetchall()]}
