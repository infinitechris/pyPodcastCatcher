import pytest

from podcast_catcher.rss import Episode, Feed, fetch_feed_data, normalize_feed_url, parse_episodes


def test_normalize_feed_url_strips_whitespace():
    assert normalize_feed_url("  https://example.com/feed.xml  ") == "https://example.com/feed.xml"


def test_episode_dataclass_fields():
    episode = Episode(title="Episode 1", link="https://example.com/1", published="2024-01-01", audio_url="https://example.com/audio.mp3")
    assert episode.title == "Episode 1"
    assert episode.link == "https://example.com/1"
    assert episode.audio_url == "https://example.com/audio.mp3"


def test_feed_dataclass_fields():
    feed = Feed(title="Example Podcast", url="https://example.com/feed.xml", description="desc")
    assert feed.title == "Example Podcast"
    assert feed.url == "https://example.com/feed.xml"
    assert feed.description == "desc"


def test_parse_episodes_detects_priority(monkeypatch):
    class FakeResponse:
        text = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Podcast</title>
    <item>
      <title>Episode 1</title>
      <link>https://example.com/1</link>
      <priority>true</priority>
      <enclosure url="https://example.com/audio.mp3" type="audio/mpeg" />
    </item>
  </channel>
</rss>'''

        def raise_for_status(self):
            return None

    monkeypatch.setattr("podcast_catcher.rss.requests.get", lambda *args, **kwargs: FakeResponse())

    episodes = parse_episodes("https://example.com/feed.xml")
    assert episodes[0].priority is True


def test_parse_episodes_respects_limit(monkeypatch):
    class FakeResponse:
        text = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Podcast</title>
    <item><title>Episode 1</title><link>https://example.com/1</link></item>
    <item><title>Episode 2</title><link>https://example.com/2</link></item>
  </channel>
</rss>'''

        def raise_for_status(self):
            return None

    monkeypatch.setattr("podcast_catcher.rss.requests.get", lambda *args, **kwargs: FakeResponse())

    episodes = parse_episodes("https://example.com/feed.xml", limit=1)

    assert [episode.title for episode in episodes] == ["Episode 1"]


def test_fetch_feed_data_rejects_non_http_url(monkeypatch):
    def fail_request(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr("podcast_catcher.rss.requests.get", fail_request)

    with pytest.raises(ValueError, match="absolute HTTP or HTTPS URL"):
        fetch_feed_data("example.com/feed.xml")
