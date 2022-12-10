import argparse
import calendar
import csv
import html
import logging
import re
import sqlite3
import threading
import time
from datetime import timedelta
from http.client import RemoteDisconnected

import feedparser
from dateutil import parser as dateparser

SITE = 'site'
ARTICLE = 'article'
SYSTEM = 'system'

IMAGE_URL_REGEX = re.compile(r'"(https?://[^"]*\.(?:png|jpg))"', re.IGNORECASE)
HTML_FIGURE_REGEX = re.compile(r'<figure>[\s\S]*?</figure>')
HTML_P_REGEX = re.compile(r'</p><p>')
HTML_TAG_REGEX = re.compile(r'<.*?>')
EXTRA_SPACE_REGEX = re.compile(r' +')
TRAILING_REPLACEMENTS = [
    (re.compile(r' Read the full article on nintendolife\.com$'), ''),
    (re.compile(r' Continue reading…$'), '.'),
    (re.compile(r'Read this article on TechRaptor$'), ''),
    (re.compile(r' View the full site RELATED LINKS:.*$'), ''),
    (re.compile(r' MORE FROM PCGAMESN: .*$'), '.'),
    (re.compile(r' Read more$'), ''),
    (re.compile(r' \[…]$'), '...')
]


def main():
    database_path, feeds_file, update_interval = parse_arguments()
    logging.info(f'Database path set to: "{database_path}"')

    db_con = sqlite3.connect(database_path)

    create_tables(db_con)

    feeds = initialize_feeds(db_con, feeds_file)
    logging.info(f'Monitoring sites: {list(feeds.keys())}')

    stop_event = threading.Event()
    update_thread = threading.Thread(target=update_feeds_loop, args=(database_path, feeds, update_interval, stop_event))

    logging.info('Starting update thread.')
    update_thread.start()

    while not stop_event.is_set():
        text = input('> Type "q" or "exit" to quit.\n')
        if text == 'q' or text == 'exit':
            stop_event.set()


def update_feeds_loop(db_path, feeds, interval: float, stop_event: threading.Event):
    db_connection = sqlite3.connect(db_path)

    while not stop_event.is_set():
        logging.info('Updating feeds.')
        success = update_feeds(db_connection, feeds)
        log_update_feeds(db_connection, success)
        logging.info('Updating feeds complete.')
        stop_event.wait(interval)


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--database-path', help='Path to the database file.', type=str, default='articles.db')
    parser.add_argument('-l', '--log-level', help='Log level for logging messages.', type=str, default='INFO',
                        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'])
    parser.add_argument('-i', '--update-interval', help='Interval between checking for news feed updates in seconds.',
                        type=float, default=60 * 60)
    parser.add_argument('feeds', help='CSV file containing on each line the feed name and feed URL.')

    args = parser.parse_args()

    loglevel = getattr(logging, args.log_level)
    logging.basicConfig(level=loglevel, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f'Set log level to: {logging.getLevelName(loglevel)}')

    return args.database_path, args.feeds, args.update_interval


def create_tables(db_connection):
    cursor = db_connection.cursor()

    if not table_exists(cursor, SITE):
        logging.info(f'{SITE} table not created yet. Creating {SITE} table.')
        cursor.execute('CREATE TABLE site ('
                       'id INTEGER PRIMARY KEY, '
                       'name TEXT, '
                       'feed TEXT, '
                       'icon TEXT, '
                       'etag TEXT, '
                       'modified TEXT'
                       ')')

    if not table_exists(cursor, ARTICLE):
        logging.info(f'{ARTICLE} table not created yet. Creating {ARTICLE} table.')
        cursor.execute('CREATE TABLE article ('
                       'id INTEGER PRIMARY KEY, '  # Artificial ID assigned to allow source independent identification
                       'original_id TEXT, '  # Article ID given by publisher
                       'site_id INTEGER REFERENCES site (id), '
                       'title TEXT, '
                       'summary TEXT, '
                       'link TEXT, '
                       'thumbnail TEXT, '
                       'published INTEGER, '
                       'author TEXT'
                       ')')

    if not table_exists(cursor, SYSTEM):
        logging.info(f'{SYSTEM} table not created yet. Creating {SYSTEM} table.')
        cursor.execute('CREATE TABLE system ('
                       'update_time INTEGER, '
                       'success INTEGER'
                       ')')

    db_connection.commit()


def initialize_feeds(db_connection, feeds_file):
    logging.info(f'Reading feeds from: "{feeds_file}"')

    with open(feeds_file) as f:
        reader = csv.reader(f)
        feeds = {name: get_site_id(db_connection, name, feed, icon) for (name, feed, icon) in reader}

    return feeds


def get_site_id(db_connection, name, feed, icon):
    """
    Returns internal site ID.
    Creates database entry if it does not yet exist and updates icon URL if it has been changed.
    """
    if not icon:
        icon = None
    cursor = db_connection.cursor()
    # Check if site already inserted
    cursor.execute("SELECT id, icon FROM site WHERE name=?", (name,))
    results = cursor.fetchall()

    if len(results) > 0:
        site_id, current_icon = results[0]
        if current_icon != icon:
            logging.info(f'Updating "{name}" site icon from "{current_icon}" to "{icon}"')
            cursor.execute("UPDATE site SET icon=? WHERE id=?", (icon, site_id))
            db_connection.commit()
        return site_id

    logging.info(f'Site "{name}" not yet in database, will be inserted with feed: "{feed}"')
    cursor.execute("INSERT INTO site (name, feed, icon) VALUES (?, ?, ?)", (name, feed, icon))
    site_id = cursor.lastrowid

    db_connection.commit()

    return site_id


def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    results = cursor.fetchall()
    return len(results) > 0


def fetch_feed(feed, etag: str = None, modified=None):
    return feedparser.parse(feed, etag=etag, modified=modified)


def update_feeds(db_connection, feeds):
    success = True
    for name, site_id in feeds.items():
        logging.info(f'Fetching articles for "{name}".')
        cursor = db_connection.cursor()
        try:
            update_feed(cursor, name, site_id)
        except AttributeError as e:
            logging.error(f'Encountered attribute error: {e}')
            db_connection.rollback()
            success = False
        except RemoteDisconnected as e:
            logging.error(f'Encountered remote disconnected: {e}')
            db_connection.rollback()
            success = False
        else:
            db_connection.commit()

    return success


def log_update_feeds(db_connection, success):
    current_time = int(time.time())
    cursor = db_connection.cursor()
    cursor.execute("INSERT INTO system (update_time, success) VALUES (?, ?)", (current_time, success))
    db_connection.commit()


def ensure_https(link: str):
    """
    Converts HTTP links into HTTPS links.
    """
    if link.startswith('http:'):
        return 'https' + link[4:]
    return link


def try_get_thumbnail(article):
    # Check for media content
    if 'media_content' in article:
        for content in article.media_content:
            return ensure_https(content['url'])

    # Check for media thumbnail
    if 'media_thumbnail' in article:
        for content in article.media_thumbnail:
            return ensure_https(content['url'])

    # Check in links
    if 'links' in article:
        for link in article.links:
            if link.type.startswith('image'):
                return ensure_https(link.href)

    # Check in summary
    matches = IMAGE_URL_REGEX.findall(article.summary)
    if len(matches) > 0:
        return ensure_https(matches[0])

    return None


def remove_html_tags(text):
    # Remove figure tags
    text = HTML_FIGURE_REGEX.sub('', text)
    # Replace change of p environment with space
    text = HTML_P_REGEX.sub(' ', text)
    # Remove remaining tags
    text = HTML_TAG_REGEX.sub('', text)
    return html.unescape(text)


def remove_extra_spaces(text):
    # Remove newlines
    text = text.replace('\n', ' ')
    # Remove tabs
    text = text.replace('\t', ' ')
    # Remove duplicate spaces
    text = EXTRA_SPACE_REGEX.sub(' ', text)
    # Remove leading and trailing spaces
    return text.strip()


def remove_trailing_message(text: str):
    """
    Removes unrelated trailing messages.
    """
    for regex, replacement in TRAILING_REPLACEMENTS:
        text = regex.sub(replacement, text)

    return text


def article_exists(cursor, article_id):
    cursor.execute('SELECT original_id FROM article WHERE original_id=?', (article_id,))
    results = cursor.fetchall()
    return len(results) > 0


def insert_article(cursor, article_id, site_id, title, summary, link, thumbnail, published, author):
    cursor.execute('INSERT INTO article (original_id, site_id, title, summary, link, thumbnail, published, author) '
                   'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (article_id, site_id, title, summary, link, thumbnail, published, author))


def update_feed(cursor, name, site_id):
    # Get etag or last modified date
    cursor.execute("SELECT feed, etag, modified FROM site WHERE id=?", (site_id,))
    (feed_url, etag, modified) = cursor.fetchall()[0]

    feed = fetch_feed(feed_url, etag, modified)

    # Check response status
    if feed.status == 304:
        logging.info(f'No new articles for "{name}".')
        return

    etag_or_modified = False

    if 'etag' in feed:
        etag_or_modified = True
        cursor.execute('UPDATE site SET etag=? WHERE id=?', (feed.etag, site_id))

    if 'modified' in feed:
        etag_or_modified = True
        cursor.execute('UPDATE site SET modified=? WHERE id=?', (feed.modified, site_id))

    if not etag_or_modified:
        logging.warning(f'"{name}" does not support etag or last modified date.')

    for article in feed.entries:
        article_id = article.id

        if article_exists(cursor, article_id):
            continue

        title = article.title
        link = article.link
        summary = remove_trailing_message(remove_extra_spaces(remove_html_tags(article.summary)))

        date = article.published_parsed if 'published_parsed' in article else article.modified_parsed
        if date is not None:
            published = calendar.timegm(date)
        else:
            logging.warning(f'No parsed date in "{name}" article "{title}".')
            # Add five hours because the only current source without parseable date is in UTC-5
            published = calendar.timegm((dateparser.parse(article.published) + timedelta(hours=5)).timetuple())
        thumbnail = try_get_thumbnail(article)

        author = article.author if 'author' in article else None

        logging.info(f'Inserting "{name}" article "{title}".')

        insert_article(cursor, article_id, site_id, title, summary, link, thumbnail, published, author)


if __name__ == '__main__':
    main()
