import json

from podcast_catcher.device_sync import export_device_dataset
from podcast_catcher.downloader import _safe_directory_name, _safe_filename_from_title
from podcast_catcher.storage import PodcastStorage


def test_export_device_dataset_copies_audio_and_stable_metadata(tmp_path):
    storage = PodcastStorage(tmp_path / "podcasts.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")
    episode_id = storage.add_episode(
        feed_id,
        "Episode 1",
        "https://example.com/episode-1",
        "2026-08-15",
        "Description",
        "https://example.com/episode-1.mp3",
    )
    storage.set_episode_playback(episode_id, 12.5, 120)

    feed_dir = _safe_directory_name("Example Podcast")
    filename = _safe_filename_from_title("Episode 1", "https://example.com/episode-1.mp3")
    source = tmp_path / "downloads" / feed_dir / filename
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake mp3 data")

    manifest_path = export_device_dataset(storage, tmp_path / "downloads", tmp_path / "export")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["episodes"][0]

    assert manifest["schema_version"] == 1
    assert entry["feed_url"] == "https://example.com/feed.xml"
    assert entry["episode_key"] == "https://example.com/episode-1.mp3"
    assert entry["relative_path"] == "media/Example Podcast/episode-1.mp3"
    assert entry["playback_position_seconds"] == 12.5
    assert (tmp_path / "export" / entry["relative_path"]).read_bytes() == b"fake mp3 data"


def test_export_device_dataset_omits_episodes_without_audio(tmp_path):
    storage = PodcastStorage(tmp_path / "podcasts.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")
    storage.add_episode(feed_id, "Not downloaded", "link", "2026-08-15", None, "https://example.com/missing.mp3")

    manifest_path = export_device_dataset(storage, tmp_path / "downloads", tmp_path / "export")

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["episodes"] == []