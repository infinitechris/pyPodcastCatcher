from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class PodcastStorage:
    def __init__(self, db_path: str | Path = "podcasts.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    description TEXT,
                    image_url TEXT,
                    download_count INTEGER NOT NULL DEFAULT 3,
                    download_filter TEXT NOT NULL DEFAULT 'all',
                    catch_up INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
            if "image_url" not in columns:
                conn.execute("ALTER TABLE feeds ADD COLUMN image_url TEXT")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
            if "download_count" not in columns:
                conn.execute("ALTER TABLE feeds ADD COLUMN download_count INTEGER NOT NULL DEFAULT 3")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
            if "download_filter" not in columns:
                conn.execute("ALTER TABLE feeds ADD COLUMN download_filter TEXT NOT NULL DEFAULT 'all'")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feeds)")}
            if "catch_up" not in columns:
                conn.execute("ALTER TABLE feeds ADD COLUMN catch_up INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    link TEXT,
                    published TEXT,
                    description TEXT,
                    audio_url TEXT,
                    priority INTEGER NOT NULL DEFAULT 0,
                    played INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    played_updated_at TEXT,
                    archived_updated_at TEXT,
                    playback_position_seconds REAL,
                    duration_seconds REAL,
                    playback_updated_at TEXT,
                    FOREIGN KEY(feed_id) REFERENCES feeds(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_state_history (
                    feed_url TEXT NOT NULL,
                    episode_key TEXT NOT NULL,
                    played INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    played_updated_at TEXT,
                    archived_updated_at TEXT,
                    PRIMARY KEY (feed_url, episode_key)
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(episodes)")}
            if "played" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN played INTEGER NOT NULL DEFAULT 0")
            if "archived" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            if "played_updated_at" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN played_updated_at TEXT")
            if "archived_updated_at" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN archived_updated_at TEXT")
            if "playback_position_seconds" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN playback_position_seconds REAL")
            if "duration_seconds" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN duration_seconds REAL")
            if "playback_updated_at" not in columns:
                conn.execute("ALTER TABLE episodes ADD COLUMN playback_updated_at TEXT")
            history_columns = {row[1] for row in conn.execute("PRAGMA table_info(episode_state_history)")}
            if "played_updated_at" not in history_columns:
                conn.execute("ALTER TABLE episode_state_history ADD COLUMN played_updated_at TEXT")
            if "archived_updated_at" not in history_columns:
                conn.execute("ALTER TABLE episode_state_history ADD COLUMN archived_updated_at TEXT")
            conn.commit()

    def _reindex_feed_ids(self) -> None:
        """Renumber feeds so IDs remain compact and sequential after adds/removals."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            feeds = conn.execute(
                "SELECT id, title, url, description, image_url, download_count, download_filter, catch_up, priority FROM feeds ORDER BY id"
            ).fetchall()

            if not feeds:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'feeds'")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.commit()
                return

            for old_id, new_id in [(row[0], idx) for idx, row in enumerate(feeds, start=1)]:
                conn.execute(
                    "UPDATE episodes SET feed_id = ? WHERE feed_id = ?",
                    (new_id, old_id),
                )

            conn.execute("DROP TABLE feeds")
            conn.execute(
                """
                CREATE TABLE feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    description TEXT,
                    image_url TEXT,
                    download_count INTEGER NOT NULL DEFAULT 3,
                    download_filter TEXT NOT NULL DEFAULT 'all',
                    catch_up INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.executemany(
                "INSERT INTO feeds (title, url, description, image_url, download_count, download_filter, catch_up, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]) for row in feeds],
            )

            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'feeds'")
            max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM feeds").fetchone()[0]
            if max_id > 0:
                conn.execute(
                    "INSERT INTO sqlite_sequence(name, seq) VALUES('feeds', ?)",
                    (max_id,),
                )

            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    def add_feed(self, title: str, url: str, description: str | None = None, priority: bool = False, image_url: str | None = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, priority FROM feeds WHERE url = ?",
                (url,),
            ).fetchone()
            if row is not None:
                feed_id = int(row[0])
                conn.execute(
                    "UPDATE feeds SET title = ?, description = ?, image_url = ?, priority = ? WHERE id = ?",
                        (title, description, image_url, int(priority or bool(row[1])), feed_id),
                )
                conn.commit()
                return feed_id

            cursor = conn.execute(
                "INSERT INTO feeds (title, url, description, image_url, priority) VALUES (?, ?, ?, ?, ?)",
                (title, url, description, image_url, int(priority)),
            )
            conn.commit()
            feed_id = int(cursor.lastrowid)
            self._reindex_feed_ids()
            return int(conn.execute("SELECT id FROM feeds WHERE url = ?", (url,)).fetchone()[0])

    def add_episode(self, feed_id: int, title: str, link: str, published: str | None, description: str | None, audio_url: str | None, priority: bool = False) -> int:
        with sqlite3.connect(self.db_path) as conn:
            feed_url = conn.execute("SELECT url FROM feeds WHERE id = ?", (feed_id,)).fetchone()[0]
            episode_key = self._episode_key(link, audio_url, title)
            state = conn.execute(
                "SELECT played, archived FROM episode_state_history WHERE feed_url = ? AND episode_key = ?",
                (feed_url, episode_key),
            ).fetchone() or (0, 0)
            cursor = conn.execute(
                """
                INSERT INTO episodes (feed_id, title, link, published, description, audio_url, priority, played, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feed_id, title, link, published, description, audio_url, int(priority), state[0], state[1]),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def add_episodes(self, feed_id: int, episodes: list[tuple[str, str, str | None, str | None, str | None, bool]]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            feed_url = conn.execute("SELECT url FROM feeds WHERE id = ?", (feed_id,)).fetchone()[0]
            conn.executemany(
                """
                INSERT INTO episodes (feed_id, title, link, published, description, audio_url, priority, played, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (feed_id, title, link, published, description, audio_url, int(priority), *(
                        conn.execute(
                            "SELECT played, archived FROM episode_state_history WHERE feed_url = ? AND episode_key = ?",
                            (feed_url, self._episode_key(link, audio_url, title)),
                        ).fetchone() or (0, 0)
                    ))
                    for title, link, published, description, audio_url, priority in episodes
                ],
            )
            conn.commit()

    @staticmethod
    def _episode_key(link: str | None, audio_url: str | None, title: str) -> str:
        return str(audio_url or link or title)

    def list_feeds(self) -> list[dict[str, str | int | None]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, url, description, image_url, download_count, download_filter, catch_up, priority FROM feeds ORDER BY id"
            ).fetchall()
        return [{"id": row[0], "title": row[1], "url": row[2], "description": row[3], "image_url": row[4], "download_count": row[5], "download_filter": row[6], "catch_up": bool(row[7]), "priority": bool(row[8])} for row in rows]

    def list_episodes(self, feed_id: int | None = None) -> list[dict[str, object]]:
        with sqlite3.connect(self.db_path) as conn:
            if feed_id is None:
                rows = conn.execute(
                    "SELECT id, feed_id, title, link, published, description, audio_url, priority, played, archived, played_updated_at, archived_updated_at, playback_position_seconds, duration_seconds, playback_updated_at FROM episodes ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, feed_id, title, link, published, description, audio_url, priority, played, archived, played_updated_at, archived_updated_at, playback_position_seconds, duration_seconds, playback_updated_at FROM episodes WHERE feed_id = ? ORDER BY id",
                    (feed_id,),
                ).fetchall()
        return [
            {
                "id": row[0],
                "feed_id": row[1],
                "title": row[2],
                "link": row[3],
                "published": row[4],
                "description": row[5],
                "audio_url": row[6],
                "priority": bool(row[7]),
                "played": bool(row[8]),
                "archived": bool(row[9]),
                "played_updated_at": row[10],
                "archived_updated_at": row[11],
                "playback_position_seconds": row[12],
                "duration_seconds": row[13],
                "playback_updated_at": row[14],
            }
            for row in rows
        ]

    def get_feed(self, feed_id: int) -> dict[str, str | int | None] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, title, url, description, image_url, download_count, download_filter, catch_up, priority FROM feeds WHERE id = ?",
                (feed_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "title": row[1], "url": row[2], "description": row[3], "image_url": row[4], "download_count": row[5], "download_filter": row[6], "catch_up": bool(row[7]), "priority": bool(row[8])}

    def set_feed_catch_up(self, feed_id: int, enabled: bool) -> None:
        with sqlite3.connect(self.db_path) as conn:
            updated = conn.execute(
                "UPDATE feeds SET catch_up = ? WHERE id = ?",
                (int(enabled), feed_id),
            ).rowcount
            if updated == 0:
                raise ValueError(f"Feed with ID {feed_id} not found")
            conn.commit()

    def set_feed_download_count(self, feed_id: int, count: int) -> None:
        if count < 1:
            raise ValueError("Download count must be at least 1")
        with sqlite3.connect(self.db_path) as conn:
            updated = conn.execute(
                "UPDATE feeds SET download_count = ? WHERE id = ?",
                (count, feed_id),
            ).rowcount
            if updated == 0:
                raise ValueError(f"Feed with ID {feed_id} not found")
            conn.commit()

    def set_feed_download_filter(self, feed_id: int, download_filter: str) -> None:
        if download_filter not in {"all", "skip_played", "skip_archived", "skip_either"}:
            raise ValueError("Invalid download filter")
        with sqlite3.connect(self.db_path) as conn:
            updated = conn.execute("UPDATE feeds SET download_filter = ? WHERE id = ?", (download_filter, feed_id)).rowcount
            if updated == 0:
                raise ValueError(f"Feed with ID {feed_id} not found")
            conn.commit()

    def get_episode(self, episode_id: int) -> dict[str, object] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, feed_id, title, link, published, description, audio_url, priority, played, archived, played_updated_at, archived_updated_at, playback_position_seconds, duration_seconds, playback_updated_at FROM episodes WHERE id = ?",
                (episode_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "feed_id": row[1],
            "title": row[2],
            "link": row[3],
            "published": row[4],
            "description": row[5],
            "audio_url": row[6],
            "priority": bool(row[7]),
            "played": bool(row[8]),
            "archived": bool(row[9]),
            "played_updated_at": row[10],
            "archived_updated_at": row[11],
            "playback_position_seconds": row[12],
            "duration_seconds": row[13],
            "playback_updated_at": row[14],
        }

    def set_episode_state(self, episode_id: int, *, played: bool | None = None, archived: bool | None = None) -> None:
        updates = []
        values: list[object] = []
        if played is not None:
            updates.append("played = ?")
            values.append(int(played))
        if archived is not None:
            updates.append("archived = ?")
            values.append(int(archived))
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            episode = conn.execute(
                "SELECT feed_id, link, audio_url, title, played, archived, played_updated_at, archived_updated_at FROM episodes WHERE id = ?",
                (episode_id,),
            ).fetchone()
            if episode is None:
                raise ValueError(f"Episode with ID {episode_id} not found")
            feed_url = conn.execute("SELECT url FROM feeds WHERE id = ?", (episode[0],)).fetchone()[0]
            new_played = int(played if played is not None else episode[4])
            new_archived = int(archived if archived is not None else episode[5])
            timestamp = datetime.now(timezone.utc).isoformat()
            if played is not None:
                updates.append("played_updated_at = ?")
                values.append(timestamp)
            if archived is not None:
                updates.append("archived_updated_at = ?")
                values.append(timestamp)
            values.append(episode_id)
            updated = conn.execute(
                f"UPDATE episodes SET {', '.join(updates)} WHERE id = ?",
                values,
            ).rowcount
            if updated == 0:
                raise ValueError(f"Episode with ID {episode_id} not found")
            conn.execute(
                "INSERT INTO episode_state_history (feed_url, episode_key, played, archived, played_updated_at, archived_updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(feed_url, episode_key) DO UPDATE SET played = excluded.played, archived = excluded.archived, played_updated_at = excluded.played_updated_at, archived_updated_at = excluded.archived_updated_at",
                (feed_url, self._episode_key(episode[1], episode[2], episode[3]), new_played, new_archived, episode[6] if played is None else timestamp, episode[7] if archived is None else timestamp),
            )
            conn.commit()

    def set_episode_playback(self, episode_id: int, position_seconds: float, duration_seconds: float | None = None) -> None:
        if position_seconds < 0 or (duration_seconds is not None and duration_seconds < 0):
            raise ValueError("Playback positions and durations cannot be negative")
        timestamp = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            updated = conn.execute(
                "UPDATE episodes SET playback_position_seconds = ?, duration_seconds = COALESCE(?, duration_seconds), playback_updated_at = ? WHERE id = ?",
                (position_seconds, duration_seconds, timestamp, episode_id),
            ).rowcount
            if updated == 0:
                raise ValueError(f"Episode with ID {episode_id} not found")
            conn.commit()

    def delete_feed(self, feed_id: int) -> None:
        """Delete a feed and all its episodes, then renumber remaining feeds to keep IDs sequential."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")

            conn.execute(
                """
                INSERT INTO episode_state_history (feed_url, episode_key, played, archived)
                SELECT f.url, COALESCE(e.audio_url, e.link, e.title), e.played, e.archived
                FROM episodes e JOIN feeds f ON f.id = e.feed_id
                WHERE e.feed_id = ? AND (e.played = 1 OR e.archived = 1)
                ON CONFLICT(feed_url, episode_key) DO UPDATE SET played = excluded.played, archived = excluded.archived
                """,
                (feed_id,),
            )

            # Delete all episodes for this feed
            conn.execute("DELETE FROM episodes WHERE feed_id = ?", (feed_id,))

            # Delete the feed
            conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))

            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

        self._reindex_feed_ids()

    def toggle_feed_priority(self, feed_id: int) -> bool:
        """Toggle the priority flag on a feed. Returns the new priority state."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT priority FROM feeds WHERE id = ?",
                (feed_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Feed with ID {feed_id} not found")
            
            current_priority = bool(row[0])
            new_priority = not current_priority
            
            conn.execute(
                "UPDATE feeds SET priority = ? WHERE id = ?",
                (int(new_priority), feed_id),
            )
            conn.commit()
            return new_priority

    def refresh_feed(self, feed_id: int | None = None, limit: int | None = None) -> int:
        """Refresh feed(s) by fetching latest episodes from RSS. Returns count of new episodes added."""
        from .rss import fetch_feed, parse_episodes
        
        new_episode_count = 0
        with sqlite3.connect(self.db_path) as conn:
            if feed_id is None:
                # Refresh all feeds
                feeds = conn.execute("SELECT id, url, priority, catch_up FROM feeds").fetchall()
            else:
                # Refresh specific feed
                feeds = conn.execute(
                    "SELECT id, url, priority, catch_up FROM feeds WHERE id = ?", (feed_id,)
                ).fetchall()
            
            for feed_row in feeds:
                feed_id_val, feed_url, feed_priority, feed_catch_up = feed_row
                try:
                    try:
                        feed = fetch_feed(feed_url)
                        if feed.image_url:
                            conn.execute(
                                "UPDATE feeds SET image_url = ? WHERE id = ?",
                                (feed.image_url, feed_id_val),
                            )
                    except Exception:
                        pass
                    episodes = parse_episodes(feed_url, limit=None if feed_catch_up else limit)
                    
                    # Check which episodes are new by audio_url
                    existing_urls = set(
                        url[0] for url in conn.execute(
                            "SELECT audio_url FROM episodes WHERE feed_id = ? AND audio_url IS NOT NULL",
                            (feed_id_val,),
                        ).fetchall()
                    )
                    
                    for episode in episodes:
                        if episode.audio_url and episode.audio_url in existing_urls:
                            continue  # Episode already exists
                        
                        # Add new episode
                        conn.execute(
                            """
                            INSERT INTO episodes (feed_id, title, link, published, description, audio_url, priority, played, archived)
                            SELECT ?, ?, ?, ?, ?, ?, ?, COALESCE(h.played, 0), COALESCE(h.archived, 0)
                            FROM (SELECT 1) AS one
                            LEFT JOIN episode_state_history h ON h.feed_url = ? AND h.episode_key = ?
                            """,
                            (
                                feed_id_val,
                                episode.title,
                                episode.link,
                                episode.published,
                                episode.description,
                                episode.audio_url,
                                int(bool(feed_priority) or episode.priority),
                                feed_url,
                                self._episode_key(episode.link, episode.audio_url, episode.title),
                            ),
                        )
                        new_episode_count += 1
                    
                    conn.commit()
                except Exception:
                    # Skip feeds that fail to parse
                    pass
        
        return new_episode_count
