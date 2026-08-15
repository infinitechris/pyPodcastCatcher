from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

import feedparser
import requests


@dataclass
class Episode:
    title: str
    link: str
    published: str | None = None
    description: str | None = None
    audio_url: str | None = None
    priority: bool = False


@dataclass
class Feed:
    title: str
    url: str
    description: str | None = None
    image_url: str | None = None


def _parse_episodes(parsed: Any, limit: int | None = None) -> list[Episode]:
    episodes: list[Episode] = []
    entries = parsed.entries if limit is None else parsed.entries[:limit]
    for entry in entries:
        audio_url = None
        enclosure = entry.get("enclosures") or []
        if enclosure:
            audio_url = enclosure[0].get("href") or enclosure[0].get("url")
        link = entry.get("link") or entry.get("id") or ""
        priority_value = entry.get("priority") or entry.get("is_priority") or entry.get("priority_flag")
        priority = False
        if isinstance(priority_value, str):
            priority = priority_value.strip().lower() in {"1", "true", "yes", "y"}
        elif isinstance(priority_value, bool):
            priority = priority_value
        episodes.append(
            Episode(
                title=entry.get("title") or "Untitled episode",
                link=link,
                published=entry.get("published") or entry.get("updated"),
                description=entry.get("summary") or entry.get("description"),
                audio_url=audio_url,
                priority=priority,
            )
        )
    return episodes


def fetch_feed_data(url: str, limit: int | None = None) -> tuple[Feed, list[Episode]]:
    parsed_url = urlparse(url.strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("feed URL must be an absolute HTTP or HTTPS URL")

    response = requests.get(url, timeout=15)
    response.raise_for_status()
    parsed = feedparser.parse(getattr(response, "content", response.text))
    episodes = _parse_episodes(parsed, limit=limit)
    if not episodes:
        raise ValueError(f"No episodes were found in the feed: {url}")

    title = parsed.feed.get("title") or urlparse(url).netloc or "Untitled feed"
    description = parsed.feed.get("description")
    image = parsed.feed.get("image")
    image_url = image.get("href") if isinstance(image, dict) else None
    return Feed(title=title, url=url, description=description, image_url=image_url), episodes


def fetch_feed(url: str) -> Feed:
    feed, _ = fetch_feed_data(url, limit=1)
    return feed


def parse_episodes(url: str, limit: int | None = None) -> list[Episode]:
    _, episodes = fetch_feed_data(url, limit=limit)
    return episodes


def normalize_feed_url(url: str) -> str:
    return url.strip()
