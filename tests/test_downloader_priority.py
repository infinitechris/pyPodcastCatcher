from pathlib import Path

from podcast_catcher.downloader import _safe_filename_from_title, download_file


def test_safe_filename_removes_apostrophes_and_periods():
    assert _safe_filename_from_title("The U.S. President's Plan", "https://example.com/audio.mp3") == "the-us-presidents-plan.mp3"


def test_download_file_prefixes_priority_name(tmp_path, monkeypatch):
    class FakeResponse:
        headers = {"Content-Length": "13"}
        content = b"audio-bytes"

        def __iter__(self):
            yield self.content

        def iter_content(self, chunk_size=65536):
            yield self.content

        def raise_for_status(self):
            return None

    monkeypatch.setattr("podcast_catcher.downloader.requests.get", lambda *args, **kwargs: FakeResponse())

    result = download_file("https://example.com/audio.mp3", tmp_path, priority=True, episode_title="Episode 1")

    assert Path(result).name == "PRIORITY_episode-1.mp3"
    assert Path(result).read_bytes() == b"audio-bytes"


def test_download_file_strips_query_string_from_filename(tmp_path, monkeypatch):
    class FakeResponse:
        headers = {"Content-Length": "13"}
        content = b"audio-bytes"

        def __iter__(self):
            yield self.content

        def iter_content(self, chunk_size=65536):
            yield self.content

        def raise_for_status(self):
            return None

    monkeypatch.setattr("podcast_catcher.downloader.requests.get", lambda *args, **kwargs: FakeResponse())

    result = download_file("https://example.com/audio.mp3?aid=rss_feed&foo=bar", tmp_path, episode_title="Episode 2")

    assert Path(result).name == "episode-2.mp3"
    assert Path(result).read_bytes() == b"audio-bytes"
