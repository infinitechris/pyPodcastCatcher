from pathlib import Path
import sqlite3

from podcast_catcher.artwork import apply_artwork, download_artwork
from podcast_catcher.downloader import _safe_directory_name, _safe_filename_from_title
from podcast_catcher.rss import fetch_feed


with sqlite3.connect("podcasts.db") as connection:
    rows = connection.execute(
        "SELECT f.title, f.image_url, e.title, e.audio_url, e.priority "
        "FROM feeds f JOIN episodes e ON e.feed_id = f.id"
    ).fetchall()

for podcast_name, image_url, episode_title, audio_url, priority in rows:
    if not image_url:
        with sqlite3.connect("podcasts.db") as lookup:
            feed_url = lookup.execute("SELECT url FROM feeds WHERE title = ?", (podcast_name,)).fetchone()[0]
        feed = fetch_feed(feed_url)
        image_url = feed.image_url
        with sqlite3.connect("podcasts.db") as update:
            update.execute("UPDATE feeds SET image_url = ? WHERE title = ?", (image_url, podcast_name))
            update.commit()
    if not image_url:
        continue
    image_path = Path("artwork") / f"{_safe_directory_name(podcast_name)}.jpg"
    if not image_path.exists():
        download_artwork(image_url, image_path)
    filename = _safe_filename_from_title(episode_title, audio_url)
    if priority:
        filename = "PRIORITY_" + filename
    file_path = Path("downloads") / _safe_directory_name(podcast_name) / filename
    if file_path.exists():
        apply_artwork(file_path, episode_title, podcast_name, image_path)
        print(f"Applied artwork: {file_path}")