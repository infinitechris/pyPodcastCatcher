from pathlib import Path

from podcast_catcher.rss import Episode
from podcast_catcher.storage import PodcastStorage


def test_storage_adds_feed_and_episode(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml", "Sample")
    episode_id = storage.add_episode(
        feed_id,
        "Episode 1",
        "https://example.com/1",
        "2024-01-01",
        "Summary",
        "https://example.com/audio.mp3",
        True,
    )

    assert feed_id > 0
    assert episode_id > 0
    assert storage.get_feed(feed_id)["title"] == "Example Podcast"
    assert storage.list_feeds()[0]["url"] == "https://example.com/feed.xml"
    assert storage.list_episodes(feed_id)[0]["title"] == "Episode 1"
    assert storage.list_episodes(feed_id)[0]["priority"] is True


def test_storage_duplicate_feed_does_not_crash(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    first_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml", "Sample", priority=True)
    second_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml", "Sample")

    assert first_id == second_id
    assert storage.get_feed(first_id)["priority"] is True


def test_storage_delete_feed_renumbers_ids(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    # Add 3 feeds
    feed_1_id = storage.add_feed("Feed 1", "https://example1.com/feed.xml")
    feed_2_id = storage.add_feed("Feed 2", "https://example2.com/feed.xml")
    feed_3_id = storage.add_feed("Feed 3", "https://example3.com/feed.xml")

    # Add episodes to feed 2
    ep_id = storage.add_episode(feed_2_id, "Episode 1", "link", "2024-01-01", "desc", "audio.mp3")

    # Verify initial state: IDs are 1, 2, 3
    feeds = storage.list_feeds()
    assert len(feeds) == 3
    assert feeds[0]["id"] == 1
    assert feeds[1]["id"] == 2
    assert feeds[2]["id"] == 3

    # Delete feed 2
    storage.delete_feed(feed_2_id)

    # After deletion, remaining feeds should be renumbered to 1, 2
    feeds = storage.list_feeds()
    assert len(feeds) == 2
    assert feeds[0]["id"] == 1
    assert feeds[1]["id"] == 2
    assert feeds[0]["title"] == "Feed 1"
    assert feeds[1]["title"] == "Feed 3"

    # Episodes for deleted feed should be gone
    assert len(storage.list_episodes()) == 0


def test_storage_list_feeds_uses_id_order_not_title_order(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    storage.add_feed("Zulu Podcast", "https://example.com/zulu.xml")
    storage.add_feed("Alpha Podcast", "https://example.com/alpha.xml")
    storage.add_feed("Middle Podcast", "https://example.com/middle.xml")

    feeds = storage.list_feeds()
    assert [feed["id"] for feed in feeds] == [1, 2, 3]
    assert [feed["title"] for feed in feeds] == ["Zulu Podcast", "Alpha Podcast", "Middle Podcast"]


def test_storage_compacts_feed_ids_after_delete_and_insert(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    storage.add_feed("Feed 1", "https://example1.com/feed.xml")
    storage.add_feed("Feed 2", "https://example2.com/feed.xml")
    storage.add_feed("Feed 3", "https://example3.com/feed.xml")

    storage.delete_feed(2)
    storage.add_feed("Feed 4", "https://example4.com/feed.xml")

    feeds = storage.list_feeds()
    assert [feed["id"] for feed in feeds] == [1, 2, 3]
    assert [feed["title"] for feed in feeds] == ["Feed 1", "Feed 3", "Feed 4"]


def test_storage_toggle_feed_priority(tmp_path):
    db_path = tmp_path / "test.db"
    storage = PodcastStorage(db_path)

    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml", "Sample", priority=False)

    # Verify initial state is not priority
    feed = storage.get_feed(feed_id)
    assert feed["priority"] is False


def test_storage_sets_feed_download_count(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")

    storage.set_feed_download_count(feed_id, 7)

    assert storage.get_feed(feed_id)["download_count"] == 7


def test_storage_sets_feed_download_filter(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")

    storage.set_feed_download_filter(feed_id, "skip_either")

    assert storage.get_feed(feed_id)["download_filter"] == "skip_either"


def test_storage_persists_episode_played_and_archived_states(tmp_path):
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

    storage.set_episode_state(episode_id, played=True, archived=True)

    episode = storage.get_episode(episode_id)
    assert episode["played"] is True
    assert episode["archived"] is True


def test_storage_persists_partial_playback_position(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Example Podcast", "https://example.com/feed.xml")
    episode_id = storage.add_episode(feed_id, "Episode 1", "link", "2024-01-01", "Description", "audio.mp3")

    storage.set_episode_playback(episode_id, 42.5, 3600)

    episode = storage.get_episode(episode_id)
    assert episode["playback_position_seconds"] == 42.5
    assert episode["duration_seconds"] == 3600
    assert episode["playback_updated_at"]


def test_episode_states_survive_feed_remove_and_readd(tmp_path):
    storage = PodcastStorage(tmp_path / "test.db")
    url = "https://example.com/feed.xml"
    feed_id = storage.add_feed("Example Podcast", url)
    episode_id = storage.add_episode(
        feed_id,
        "Episode 1",
        "https://example.com/1",
        "2024-01-01",
        "Description",
        "https://example.com/1.mp3",
    )
    storage.set_episode_state(episode_id, played=True, archived=True)

    storage.delete_feed(feed_id)
    new_feed_id = storage.add_feed("Example Podcast", url)
    restored_id = storage.add_episode(
        new_feed_id,
        "Episode 1",
        "https://example.com/1",
        "2024-01-01",
        "Description",
        "https://example.com/1.mp3",
    )

    restored = storage.get_episode(restored_id)
    assert restored["played"] is True
    assert restored["archived"] is True

    # Toggle to priority
    new_priority = storage.toggle_feed_priority(feed_id)
    assert new_priority is True
    feed = storage.get_feed(feed_id)
    assert feed["priority"] is True

    # Toggle back to non-priority
    new_priority = storage.toggle_feed_priority(feed_id)
    assert new_priority is False
    feed = storage.get_feed(feed_id)
    assert feed["priority"] is False


def test_refresh_applies_feed_priority_to_new_episodes(tmp_path, monkeypatch):
    storage = PodcastStorage(tmp_path / "test.db")
    feed_id = storage.add_feed("Priority Podcast", "https://example.com/feed.xml", priority=True)

    monkeypatch.setattr(
        "podcast_catcher.rss.parse_episodes",
        lambda url, limit=None: [
            Episode(
                title="New episode",
                link="https://example.com/episode",
                audio_url="https://example.com/episode.mp3",
            )
        ],
    )

    assert storage.refresh_feed(feed_id) == 1
    assert storage.list_episodes(feed_id)[0]["priority"] is True
