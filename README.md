# NewsFeeder

Collects news items from RSS and Atom feeds.

## Collection

Running `python main.py feeds.csv` starts the collection process, which can be exited by typing `q`. Polls RSS/Atom
feeds every hour by default, taking advantage of etags and last modified dates where supported. Data is stored in a
SQLite DB (default: articles.db).

## API

An API is provided by the Flask server specified in `plate/`, which can be run with `export FLASK_APP=plate;flask run`.
The supported endpoints are:

- `<host>/sites`: `{"sites": [{"site": <site_name>, "id": <site_id>}, ...]}`
- `<host>/articles/<sites>/<n_articles>/<last_article_published>`:
  ```json
  {"articles": [{
    "site": <site_name>,
    "title": <article_title>,
    "summary": <article_summary>,
    "link": <article_url>,
    "thumbnail": <thumbnail_url>,
    "author": <article_author>,
    "published": <publish_date_unix_timestamp>
  }, ...]}
  ```
  Where `<sites>` is a comma separated list of site IDs or `all` and `<last_article_published>` is the optional unix
  timestamp all returned articles should be published before.

## Deploying with uWSGI and NGINX

In addition to the requirements in `requirements.txt`, you will need to install uWSGI using pip:

```shell
pip install uwsgi
```

Install NGINX.

Adjust `service/newsfeeder.service` by replacing `user` with your username and `/path/to/newsfeeder` with the path to
this repository. Move this file to `/etc/systemd/system/`.

Move `service/newsfeeder` to `/etc/nginx/sites-available/` and enable it by linking it
into `/etc/nginx/sites-enabled/` (you may need to unlink the default site).

Start both the nginx and newsfeeder services (the nginx service may be already running and may need to be restarted).
```shell
sudo systemctl start newsfeeder
sudo systemctl restart nginx
```