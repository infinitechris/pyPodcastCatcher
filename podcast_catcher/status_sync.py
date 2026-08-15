from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .storage import PodcastStorage


STATUS_FILENAME = "podcast-status.json"
HASH_FILENAME = "podcast-status.sha1"


def _episode_key(episode: dict[str, object]) -> str:
    return str(episode.get("audio_url") or episode.get("link") or episode.get("title"))


def build_manifest(storage: PodcastStorage) -> dict[str, Any]:
    episodes: dict[str, dict[str, object]] = {}
    feeds = {int(feed["id"]): str(feed["url"]) for feed in storage.list_feeds()}
    for episode in storage.list_episodes():
        feed_url = feeds.get(int(episode["feed_id"]))
        if feed_url is None:
            continue
        episodes[f"{feed_url}|{_episode_key(episode)}"] = {
            "feed_url": feed_url,
            "episode_key": _episode_key(episode),
            "played": bool(episode["played"]),
            "archived": bool(episode["archived"]),
            "played_updated_at": episode.get("played_updated_at"),
            "archived_updated_at": episode.get("archived_updated_at"),
            "playback_position_seconds": episode.get("playback_position_seconds"),
            "duration_seconds": episode.get("duration_seconds"),
            "playback_updated_at": episode.get("playback_updated_at"),
        }
    return {"version": 1, "episodes": episodes}


def _json_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def export_status(storage: PodcastStorage, directory: str | Path = "downloads") -> tuple[Path, Path]:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / STATUS_FILENAME
    hash_path = destination / HASH_FILENAME
    data = _json_bytes(build_manifest(storage))
    manifest_path.write_bytes(data)
    hash_path.write_text(hashlib.sha1(data).hexdigest() + "  " + manifest_path.name + "\n", encoding="ascii")
    return manifest_path, hash_path


def inspect_status(storage: PodcastStorage, directory: str | Path = "downloads") -> str | None:
    destination = Path(directory)
    manifest_path = destination / STATUS_FILENAME
    hash_path = destination / HASH_FILENAME
    if not manifest_path.exists() and not hash_path.exists():
        return None
    if not manifest_path.exists() or not hash_path.exists():
        return "status manifest or hash is missing"
    try:
        data = manifest_path.read_bytes()
        expected = hash_path.read_text(encoding="ascii").split()[0]
        actual = hashlib.sha1(data).hexdigest()
        if expected == actual:
            return None
        manifest = json.loads(data.decode("utf-8"))
        current = build_manifest(storage)
        if manifest != current:
            return "status manifest hash failed and it differs from the desktop database"
        return "status manifest hash failed, but its content matches the desktop database"
    except (OSError, ValueError, json.JSONDecodeError, IndexError):
        return "status manifest could not be validated"