from datetime import datetime

from flask import Blueprint

from plate.db import get_db

bp = Blueprint('system', __name__, url_prefix='/system')


@bp.route("/status")
def request_sites():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT update_time, success FROM system ORDER BY update_time DESC LIMIT 1')
    results = cursor.fetchall()
    if len(results) == 0:
        last_updated = None
        last_updated_string = 'Never'
        success = None
    else:
        last_updated, success = results[0]
        last_updated_string = datetime.utcfromtimestamp(last_updated).strftime('%d.%m.%Y %H:%M (UTC)')
    return {'last_updated': last_updated, 'last_updated_string': last_updated_string, 'success': bool(success)}
