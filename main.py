import argparse
import csv
import html
import logging
import re
import sqlite3
import threading
import time

import feedparser
from dateutil import parser as dateparser

SITE = 'site'
ARTICLE = 'article'

IMAGE_URL_REGEX = re.compile(r'"(https?://[^"]*\.(?:png|jpg))"', re.IGNORECASE)
HTML_TAG_REGEX = re.compile(r'<.*?>')
EXTRA_SPACE_REGEX = re.compile(r' +')


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
        update_feeds(db_connection, feeds)
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
        cursor.execute('CREATE TABLE site (name TEXT, id INTEGER PRIMARY KEY, feed TEXT, etag TEXT, modified TEXT)')

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

    db_connection.commit()


def initialize_feeds(db_connection, feeds_file):
    logging.info(f'Reading feeds from: "{feeds_file}"')

    with open(feeds_file) as f:
        reader = csv.reader(f)
        feeds = {name: get_site_id(db_connection, name, feed) for (name, feed) in reader}

    return feeds


def get_site_id(db_connection, name, feed):
    cursor = db_connection.cursor()
    # Check if site already inserted
    cursor.execute(f"SELECT id FROM site WHERE name=?", (name,))
    site_id = cursor.fetchall()

    if len(site_id) == 0:
        logging.info(f'Site "{name}" not yet in database, will be inserted with feed: "{feed}"')
        cursor.execute(f'INSERT INTO site (name, feed) VALUES (?, ?)', (name, feed))
        cursor.execute(f'SELECT id FROM site WHERE name=?', (name,))
        site_id = cursor.fetchall()

    db_connection.commit()

    return site_id[0][0]


def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    results = cursor.fetchall()
    return len(results) > 0


def fetch_feed(feed, etag: str = None, modified=None):
    return feedparser.parse(feed, etag=etag, modified=modified)


def update_feeds(db_connection, feeds):
    for name, site_id in feeds.items():
        logging.info(f'Fetching articles for "{name}".')
        cursor = db_connection.cursor()

        update_feed(cursor, name, site_id)

        db_connection.commit()


def try_get_thumbnail(article):
    # Check for media content
    if 'media_content' in article:
        for content in article.media_content:
            return content['url']

    # Check for media thumbnail
    if 'media_thumbnail' in article:
        for content in article.media_thumbnail:
            return content['url']

    # Check in links
    if 'links' in article:
        for link in article.links:
            if link.type.startswith('image'):
                return link.href

    # Check in summary
    matches = IMAGE_URL_REGEX.findall(article.summary)
    if len(matches) > 0:
        return matches[0]

    return None


def remove_html_tags(text):
    return html.unescape(HTML_TAG_REGEX.sub(' ', text))


def remove_extra_spaces(text):
    return EXTRA_SPACE_REGEX.sub(' ', text.replace('\n', ' '))


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
        summary = remove_extra_spaces(remove_html_tags(article.summary))

        date = article.published_parsed if 'published_parsed' in article else article.modified_parsed
        if date is not None:
            published = int(time.mktime(date))
        else:
            logging.warning(f'No parsed date in "{name}" article "{title}".')
            published = int(time.mktime(dateparser.parse(article.published).timetuple()))
        thumbnail = try_get_thumbnail(article)

        author = article.author if 'author' in article else None

        logging.info(f'Inserting "{name}" article "{title}".')

        insert_article(cursor, article_id, site_id, title, summary, link, thumbnail, published, author)


if __name__ == '__main__':
    main()
