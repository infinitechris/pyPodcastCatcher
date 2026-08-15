import hashlib
import json

from podcast_catcher.status_sync import export_status, inspect_status
from podcast_catcher.storage import PodcastStorage


def test_status_export_writes_json_and_sha1(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")
    episode_id = storage.add_episode(
        feed_id,
        "Episode 1",
        "https://example.com/1",
        "2024-01-01",
        "Description",
        "https://example.com/1.mp3",
    )
    storage.set_episode_state(episode_id, played=True)

    manifest_path, hash_path = export_status(storage, tmp_path / "downloads")
    data = manifest_path.read_bytes()

    assert hash_path.read_text(encoding="ascii").startswith(hashlib.sha1(data).hexdigest())
    assert json.loads(data)["episodes"]
    assert inspect_status(storage, tmp_path / "downloads") is None


def test_status_hash_failure_compares_manifest_with_database(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")
    storage.add_episode(feed_id, "Episode 1", "link", "2024-01-01", "Description", "audio.mp3")
    manifest_path, hash_path = export_status(storage, tmp_path / "downloads")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(iter(manifest["episodes"].values()))["played"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    warning = inspect_status(storage, tmp_path / "downloads")
    assert warning == "status manifest hash failed and it differs from the desktop database"