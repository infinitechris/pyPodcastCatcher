from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .downloader import _safe_directory_name, _safe_filename_from_title
from .storage import PodcastStorage


DEVICE_MANIFEST_VERSION = 1


def _episode_key(episode: dict[str, object]) -> str:
    return str(episode.get("audio_url") or episode.get("link") or episode.get("title"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_device_manifest(storage: PodcastStorage, downloads_dir: str | Path = "downloads") -> dict[str, Any]:
    downloads_root = Path(downloads_dir)
    feeds = {int(feed["id"]): feed for feed in storage.list_feeds()}
    episodes: list[dict[str, Any]] = []

    for episode in storage.list_episodes():
        feed = feeds.get(int(episode["feed_id"]))
        if feed is None or not episode.get("audio_url"):
            continue

        feed_directory = _safe_directory_name(str(feed["title"]))
        filename = _safe_filename_from_title(str(episode["title"]), str(episode["audio_url"]))
        if episode.get("priority"):
            stem, suffix = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = f"PRIORITY_{stem}{'.' + suffix if suffix else ''}"

        source_path = downloads_root / feed_directory / filename
        if not source_path.is_file():
            continue

        episodes.append(
            {
                "feed_url": str(feed["url"]),
                "episode_key": _episode_key(episode),
                "podcast_title": str(feed["title"]),
                "episode_title": str(episode["title"]),
                "published": episode.get("published"),
                "relative_path": (Path("media") / feed_directory / filename).as_posix(),
                "byte_size": source_path.stat().st_size,
                "sha256": _sha256(source_path),
                "priority": bool(episode.get("priority")),
                "played": bool(episode.get("played")),
                "archived": bool(episode.get("archived")),
                "playback_position_seconds": episode.get("playback_position_seconds"),
                "duration_seconds": episode.get("duration_seconds"),
                "playback_updated_at": episode.get("playback_updated_at"),
            }
        )

    episodes.sort(key=lambda item: (item["feed_url"], item["episode_key"]))
    return {
        "schema_version": DEVICE_MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "pyPodcastCatcher",
        "episodes": episodes,
    }


def export_device_dataset(
    storage: PodcastStorage,
    downloads_dir: str | Path = "downloads",
    output_dir: str | Path = "device-export",
) -> Path:
    downloads_root = Path(downloads_dir)
    destination = Path(output_dir)
    manifest = build_device_manifest(storage, downloads_root)

    for episode in manifest["episodes"]:
        relative_path = Path(str(episode["relative_path"]))
        source = downloads_root / relative_path.relative_to("media")
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def sync_device_root(
    storage: PodcastStorage,
    downloads_dir: str | Path = "downloads",
    target_root: str | Path = ".",
    dataset_dirname: str = "device-export",
) -> tuple[Path, Path, Path, Path]:
    target = Path(target_root)
    dataset_root = target / dataset_dirname
    dataset_root.mkdir(parents=True, exist_ok=True)

    manifest_path = export_device_dataset(storage, downloads_dir, dataset_root)
    status_manifest_path, status_hash_path = export_status(storage, target)

    return manifest_path, dataset_root, status_manifest_path, status_hash_path