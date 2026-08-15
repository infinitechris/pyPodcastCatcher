from __future__ import annotations

import argparse
import msvcrt
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .downloader import _safe_directory_name, download_file
from .artwork import download_artwork
from .device_sync import export_device_dataset
from .rss import fetch_feed_data
from .status_sync import export_status, inspect_status
from .storage import PodcastStorage

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="podcast-catcher", description="Simple podcast feed manager.")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add a podcast feed")
    add_parser.add_argument("url", help="RSS feed URL")
    add_parser.add_argument("--name", dest="name", help="Optional feed name")
    add_parser.add_argument("--priority", action="store_true", help="Mark this podcast as a priority feed")
    add_parser.set_defaults(func=handle_add)

    list_parser = subparsers.add_parser("list", help="List feeds or episodes")
    list_parser.add_argument("kind", nargs="?", default="feeds", choices=["feeds", "episodes"], help="What to list (default: feeds)")
    list_parser.add_argument("--feed-id", dest="feed_id", type=int, help="Filter episodes by feed ID")
    list_parser.set_defaults(func=handle_list)

    download_parser = subparsers.add_parser("download", help="Download an episode or all episodes across all feeds")
    download_parser.add_argument("feed_id", nargs="?", type=int, help="Feed ID")
    download_parser.add_argument("episode_index", nargs="?", type=int, help="Episode index in the feed list")
    download_parser.add_argument("--destination", default="./downloads", help="Download directory")
    download_parser.add_argument("--count", type=int, default=3, help="Number of newest episodes to download per feed (default: 3)")
    download_parser.set_defaults(func=handle_download)

    remove_parser = subparsers.add_parser("remove", help="Remove a subscribed feed")
    remove_parser.add_argument("feed_id", nargs="?", type=int, help="Feed ID to remove")
    remove_parser.set_defaults(func=handle_remove)

    toggle_parser = subparsers.add_parser("toggle", help="Toggle priority flag on a feed")
    toggle_parser.add_argument("feed_id", nargs="?", type=int, help="Feed ID to toggle")
    toggle_parser.set_defaults(func=handle_toggle)

    refresh_parser = subparsers.add_parser("refresh", help="Refresh feeds to fetch latest episodes")
    refresh_parser.add_argument("feed_id", nargs="?", type=int, help="Feed ID to refresh (default: all feeds)")
    refresh_parser.set_defaults(func=handle_refresh)

    watch_parser = subparsers.add_parser("watch", help="Poll feeds and download newly detected episodes")
    watch_parser.add_argument("--interval", type=float, default=900, help="Seconds between feed checks (default: 900)")
    watch_parser.add_argument("--destination", default="./downloads", help="Download directory")
    watch_parser.add_argument("--once", action="store_true", help="Check feeds once, then exit")
    watch_parser.set_defaults(func=handle_watch)

    export_parser = subparsers.add_parser("export-device", help="Export downloaded episodes for esPod")
    export_parser.add_argument("--downloads", default="./downloads", help="Source download directory")
    export_parser.add_argument("--output", default="./device-export", help="Output dataset directory")
    export_parser.set_defaults(func=handle_export_device)

    return parser


def ensure_storage() -> PodcastStorage:
    return PodcastStorage("podcasts.db")


def handle_add(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    try:
        feed, episodes = fetch_feed_data(args.url, limit=1)
    except requests.exceptions.Timeout:
        console.print("[red]Could not add feed: the request timed out.[/red]")
        return 1
    except requests.exceptions.ConnectionError:
        console.print("[red]Could not add feed: the host could not be reached.[/red]")
        return 1
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        console.print(f"[red]Could not add feed: the server returned HTTP {status}.[/red]")
        return 1
    except requests.exceptions.RequestException as exc:
        console.print(f"[red]Could not add feed: {exc}[/red]")
        return 1
    except ValueError as exc:
        console.print(f"[red]Could not add feed: {exc}[/red]")
        return 1
    title = args.name or feed.title
    feed_id = storage.add_feed(title, args.url, feed.description, priority=args.priority, image_url=feed.image_url)

    if feed.image_url:
        try:
            download_artwork(feed.image_url, Path("artwork") / f"{_safe_directory_name(title)}.jpg")
        except requests.RequestException as exc:
            console.print(f"[yellow]Could not download podcast artwork: {exc}[/yellow]")

    storage.add_episodes(
        feed_id,
        [
            (
                episode.title,
                episode.link,
                episode.published,
                episode.description,
                episode.audio_url,
                bool(args.priority or episode.priority),
            )
            for episode in episodes
        ],
    )

    console.print(f"Added feed '{title}' with ID {feed_id}")
    return 0


def handle_list(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    if args.kind == "feeds":
        rows = storage.list_feeds()
        if not rows:
            console.print("No feeds saved yet.")
            return 0
        table = Table(title="Feeds")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Priority", style="yellow")
        table.add_column("URL")
        for row in rows:
            priority_icon = "★" if row["priority"] else ""
            table.add_row(str(row["id"]), str(row["title"]), priority_icon, str(row["url"]))
        console.print(table)
        return 0

    episodes = storage.list_episodes(args.feed_id)
    if not episodes:
        console.print("No episodes found.")
        return 0
    table = Table(title="Episodes")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Published")
    table.add_column("Played")
    table.add_column("Archived")
    table.add_column("Audio URL")
    for row in episodes:
        table.add_row(
            str(row["id"]),
            str(row["title"]),
            str(row["published"] or ""),
            "Yes" if row["played"] else "No",
            "Yes" if row["archived"] else "No",
            str(row["audio_url"] or ""),
        )
    console.print(table)
    return 0


def _prompt_force_redownload(episode_title: str, podcast_title: str, path: Path) -> bool:
    response = input(
        f"Episode '{episode_title}' from '{podcast_title}' already exists. Force re-download? [y/N]: "
    ).strip().lower()
    return response in {"y", "yes"}


def _allows_download(feed: dict[str, object], episode: dict[str, object]) -> bool:
    download_filter = feed.get("download_filter", "all")
    if download_filter == "skip_played" and episode.get("played"):
        return False
    if download_filter == "skip_archived" and episode.get("archived"):
        return False
    if download_filter == "skip_either" and (episode.get("played") or episode.get("archived")):
        return False
    return True


def _confirm_feed_removal(feed_title: str) -> bool:
    response = input(
        f"WARNING: This will permanently delete the feed '{feed_title}' and all of its episodes. This cannot be undone. Continue? [y/N]: "
    ).strip().lower()
    return response in {"y", "yes"}

    def _confirm_catch_up(feed_title: str) -> bool:
        response = input(
            f"Enable catch-up mode for '{feed_title}'? This may fetch the full available archive. [y/N]: "
        ).strip().lower()
        return response in {"y", "yes"}


def handle_download(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    destination = Path(args.destination)
    failed_downloads = []  # Track episodes that fail during download
    refresh_limit = None if args.episode_index is not None else args.count

    # Refresh feeds in background to get latest episodes
    if args.feed_id is None:
        # Refreshing all feeds before downloading from all
        new_count = storage.refresh_feed(None, limit=refresh_limit)
        if new_count > 0:
            console.print(f"[cyan]Updated feeds: found {new_count} new episode(s)[/cyan]")
    else:
        # Refreshing specific feed
        new_count = storage.refresh_feed(args.feed_id, limit=refresh_limit)
        if new_count > 0:
            console.print(f"[cyan]Updated feed: found {new_count} new episode(s)[/cyan]")

    def do_download(audio_url: str, episode_title: str, podcast_title: str, priority: bool, artwork_url: str | None = None, retry: bool = False) -> bool:
        """Download an episode. Returns True if successful, False if failed. Adds to retry list on HTTP error."""
        try:
            file_path = download_file(
                str(audio_url),
                destination,
                priority=priority,
                podcast_name=str(podcast_title),
                episode_title=episode_title,
                artwork_url=artwork_url,
            )
            console.print(f"Downloaded '{episode_title}' to {file_path}")
            return True
        except FileExistsError as exc:
            path_text = str(exc).split("File already exists: ", 1)[1] if "File already exists:" in str(exc) else str(destination / podcast_title / episode_title)
            file_path = Path(path_text)
            if not _prompt_force_redownload(episode_title, podcast_title, file_path):
                console.print(f"Skipped '{episode_title}' because it already exists.")
                return True  # Consider as success since user chose to skip
            file_path = download_file(
                str(audio_url),
                destination,
                priority=priority,
                podcast_name=str(podcast_title),
                force=True,
                episode_title=episode_title,
            )
            console.print(f"Re-downloaded '{episode_title}' to {file_path}")
            return True
        except requests.exceptions.HTTPError as e:
            console.print(f"[red]Failed to download '{episode_title}' (HTTP {e.response.status_code})[/red]")
            if not retry:
                # Only add to retry list if this is not a retry attempt
                failed_downloads.append((audio_url, episode_title, podcast_title, priority))
            return False
        except Exception as e:
            console.print(f"[red]Error downloading '{episode_title}': {e}[/red]")
            return False

    if args.feed_id is None and args.episode_index is None:
        feed_rows = storage.list_feeds()
        if not feed_rows:
            console.print("No feeds saved yet.")
            return 1
        for feed in feed_rows:
            feed_id = int(feed["id"])
            episodes = storage.list_episodes(feed_id)
            # Sort by published date (newest first) and limit to count
            episodes_sorted = sorted(
                episodes,
                key=lambda e: e.get("published") or "",
                reverse=True,
            )
            episodes_to_download = episodes_sorted[: args.count]
            for episode in episodes_to_download:
                if not _allows_download(feed, episode):
                    continue
                audio_url = episode.get("audio_url")
                if not audio_url:
                    continue
                do_download(
                    str(audio_url),
                    str(episode.get("title", "Untitled episode")),
                    str(feed["title"]),
                    bool(episode.get("priority", False)),
                    feed.get("image_url"),
                )
        
        # Retry failed episodes after initial queue
        if failed_downloads:
            console.print("\n[yellow]Retrying failed episodes...[/yellow]")
            for audio_url, episode_title, podcast_title, priority in failed_downloads:
                do_download(audio_url, episode_title, podcast_title, priority, retry=True)
        
        return 0

    if args.feed_id is None or args.episode_index is None:
        # If feed_id is provided but no episode_index, download newest N episodes from that feed
        if args.feed_id is not None and args.episode_index is None:
            episodes = storage.list_episodes(args.feed_id)
            if not episodes:
                console.print("No episodes for that feed.")
                return 1
            feed = storage.get_feed(args.feed_id)
            if feed is None:
                console.print(f"No feed found with ID {args.feed_id}.")
                return 1
            # Sort by published date (newest first) and limit to count
            episodes_sorted = sorted(
                episodes,
                key=lambda e: e.get("published") or "",
                reverse=True,
            )
            episodes_to_download = episodes_sorted[: args.count]
            for episode in episodes_to_download:
                if not _allows_download(feed, episode):
                    continue
                audio_url = episode.get("audio_url")
                if not audio_url:
                    continue
                do_download(
                    str(audio_url),
                    str(episode.get("title", "Untitled episode")),
                    str(feed["title"]),
                    bool(episode.get("priority", False)),
                    feed.get("image_url"),
                )
            
            # Retry failed episodes after initial queue
            if failed_downloads:
                console.print("\n[yellow]Retrying failed episodes...[/yellow]")
                for audio_url, episode_title, podcast_title, priority in failed_downloads:
                    do_download(audio_url, episode_title, podcast_title, priority, retry=True)
            
            return 0
        # If only episode_index is provided without feed_id, that's an error
        console.print("Provide either no arguments to download the newest episodes, or both a feed_id and episode_index for a specific episode.")
        return 1

    episodes = storage.list_episodes(args.feed_id)
    if not episodes:
        console.print("No episodes for that feed.")
        return 1
    if args.episode_index < 0 or args.episode_index >= len(episodes):
        console.print(f"Episode index {args.episode_index} is out of range for feed {args.feed_id}.")
        return 1

    episode = episodes[args.episode_index]
    audio_url = episode["audio_url"]
    if not audio_url:
        console.print(f"Episode '{episode['title']}' does not have an audio URL.")
        return 1

    podcast_title = storage.get_feed(args.feed_id)["title"] if storage.get_feed(args.feed_id) else "podcast"
    do_download(
        str(audio_url),
        str(episode.get("title", "Untitled episode")),
        str(podcast_title),
        bool(episode.get("priority", False)),
        storage.get_feed(args.feed_id).get("image_url") if storage.get_feed(args.feed_id) else None,
    )
    return 0


def handle_remove(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    feed_rows = storage.list_feeds()
    if not feed_rows:
        console.print("No feeds saved yet.")
        return 0

    if args.feed_id is not None:
        selected = next((feed for feed in feed_rows if int(feed["id"]) == args.feed_id), None)
        if selected is None:
            console.print(f"No feed found with ID {args.feed_id}.")
            return 1
    else:
        table = Table(title="Select a feed to remove")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        for row in feed_rows:
            table.add_row(str(row["id"]), str(row["title"]))
        console.print(table)
        chosen = input("Enter feed ID to remove: ").strip()
        if not chosen:
            console.print("No feed selected.")
            return 0
        try:
            selected_id = int(chosen)
        except ValueError:
            console.print("Feed ID must be an integer.")
            return 1
        selected = next((feed for feed in feed_rows if int(feed["id"]) == selected_id), None)
        if selected is None:
            console.print(f"No feed found with ID {selected_id}.")
            return 1

    feed_title = str(selected["title"])
    if not _confirm_feed_removal(feed_title):
        console.print("Feed removal cancelled.")
        return 0

    feed_id = int(selected["id"])
    storage.delete_feed(feed_id)

    console.print(f"Deleted feed '{feed_title}' and all related episodes.")
    return 0


def handle_toggle(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    feed_rows = storage.list_feeds()
    if not feed_rows:
        console.print("No feeds saved yet.")
        return 0

    if args.feed_id is not None:
        selected = next((feed for feed in feed_rows if int(feed["id"]) == args.feed_id), None)
        if selected is None:
            console.print(f"No feed found with ID {args.feed_id}.")
            return 1
    else:
        table = Table(title="Select a feed to toggle priority")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Priority", style="yellow")
        for row in feed_rows:
            priority_icon = "★" if row["priority"] else ""
            table.add_row(str(row["id"]), str(row["title"]), priority_icon)
        console.print(table)
        chosen = input("Enter feed ID to toggle: ").strip()
        if not chosen:
            console.print("No feed selected.")
            return 0
        try:
            selected_id = int(chosen)
        except ValueError:
            console.print("Feed ID must be an integer.")
            return 1
        selected = next((feed for feed in feed_rows if int(feed["id"]) == selected_id), None)
        if selected is None:
            console.print(f"No feed found with ID {selected_id}.")
            return 1

    feed_id = int(selected["id"])
    feed_title = str(selected["title"])
    try:
        new_priority = storage.toggle_feed_priority(feed_id)
    except ValueError as e:
        console.print(f"Error: {e}")
        return 1

    status = "enabled" if new_priority else "disabled"
    console.print(f"Priority {status} for feed '{feed_title}'.")
    return 0


def handle_refresh(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    
    if args.feed_id is None:
        # Refresh all feeds
        feed_rows = storage.list_feeds()
        if not feed_rows:
            console.print("No feeds saved yet.")
            return 0
        new_count = storage.refresh_feed(None)
        console.print(f"Refreshed all feeds: found {new_count} new episode(s)")
        return 0
    
    # Refresh specific feed
    feed = storage.get_feed(args.feed_id)
    if feed is None:
        console.print(f"No feed found with ID {args.feed_id}.")
        return 1


    new_count = storage.refresh_feed(args.feed_id)
    console.print(f"Refreshed feed '{feed['title']}': found {new_count} new episode(s)")
    return 0


def handle_export_device(args: argparse.Namespace) -> int:
    manifest_path = export_device_dataset(ensure_storage(), args.downloads, args.output)
    console.print(f"Exported device dataset to {manifest_path.parent}.")
    return 0


def _view_feed_episodes(storage: PodcastStorage, feed_id: int) -> None:
    selected = 0
    page = 0
    page_size = 10
    while True:
        episodes = storage.list_episodes(feed_id)
        if not episodes:
            console.print("No episodes found.")
            input("Press Enter to return...")
            return
        start = page * page_size
        visible_episodes = episodes[start:start + page_size]
        has_more = start + page_size < len(episodes)
        selected = min(selected, len(visible_episodes) if has_more else len(visible_episodes) - 1)
        os.system("cls")
        feed = storage.get_feed(feed_id)
        console.print(f"[bold]{feed['title'] if feed else 'Podcast'} episodes[/bold]\n")
        for index, episode in enumerate(visible_episodes):
            marker = ">" if index == selected else " "
            states = f"[played={'yes' if episode['played'] else 'no'}, archived={'yes' if episode['archived'] else 'no'}]"
            console.print(f"{marker} {episode['title']} {states}")
        if has_more:
            marker = ">" if selected == len(visible_episodes) else " "
            console.print(f"{marker} MORE >")
        console.print("\nEnter: episode actions | Esc: back")
        key = msvcrt.getwch()
        if key == "\x03":
            raise KeyboardInterrupt
        if key == "\x1b":
            return
        if key in {"\x00", "\xe0"}:
            key = msvcrt.getwch()
            if key == "H":
                selected = (selected - 1) % (len(visible_episodes) + int(has_more))
            elif key == "P":
                selected = (selected + 1) % (len(visible_episodes) + int(has_more))
            continue
        if key != "\r":
            continue

        if has_more and selected == len(visible_episodes):
            page += 1
            selected = 0
            continue

        episode = visible_episodes[selected]
        played_state = "On" if episode["played"] else "Off"
        archived_state = "On" if episode["archived"] else "Off"
        actions = [
            f"Played: {played_state} -> {'Off' if episode['played'] else 'On'}",
            f"Archived: {archived_state} -> {'Off' if episode['archived'] else 'On'}",
        ]
        action = 0
        while True:
            os.system("cls")
            console.print(f"[bold]{episode['title']}[/bold]\n")
            for index, label in enumerate(actions):
                console.print(f"{'>' if index == action else ' '} {label}")
            console.print("\nSelect Played or Archived to toggle it. Esc: back")
            key = msvcrt.getwch()
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x1b":
                break
            if key in {"\x00", "\xe0"}:
                key = msvcrt.getwch()
                if key in {"H", "P"}:
                    action = 1 - action
                continue
            if key != "\r":
                continue
            if action == 0:
                storage.set_episode_state(int(episode["id"]), played=not bool(episode["played"]))
            else:
                storage.set_episode_state(int(episode["id"]), archived=not bool(episode["archived"]))
            break


def _episode_identity(episode: dict[str, object]) -> str:
    return str(episode.get("audio_url") or episode.get("link") or episode.get("title"))


def _watch_once(storage: PodcastStorage, destination: Path) -> list[str]:
    feeds = storage.list_feeds()
    before = {
        int(feed["id"]): {
            _episode_identity(episode)
            for episode in storage.list_episodes(int(feed["id"]))
        }
        for feed in feeds
    }

    storage.refresh_feed(None, limit=3)
    downloaded: list[str] = []

    for feed in storage.list_feeds():
        feed_id = int(feed["id"])
        known = before.get(feed_id, set())
        new_episodes = [
            episode
            for episode in storage.list_episodes(feed_id)
            if _episode_identity(episode) not in known
        ]
        new_episodes.sort(key=lambda episode: episode.get("published") or "", reverse=True)
        for episode in new_episodes:
            if not _allows_download(feed, episode):
                continue
            audio_url = episode.get("audio_url")
            if not audio_url:
                continue
            try:
                download_file(
                    str(audio_url),
                    destination,
                    priority=bool(episode.get("priority", False)),
                    podcast_name=str(feed["title"]),
                    episode_title=str(episode.get("title", "Untitled episode")),
                    artwork_url=feed.get("image_url"),
                    show_progress=False,
                )
                downloaded.append(f"{feed['title']}: {episode.get('title', 'Untitled episode')}")
            except FileExistsError:
                pass
            except Exception:
                pass
    return downloaded


def _write_watch_status(message: str, live: Live) -> None:
    live.update(message)


def handle_watch(args: argparse.Namespace) -> int:
    storage = ensure_storage()
    try:
        with Live("Watching all feeds.", console=console, refresh_per_second=4) as live:
            next_check = time.monotonic()
            while True:
                check_started = time.monotonic()
                downloaded = _watch_once(storage, Path(args.destination))
                if downloaded:
                    result = f"Downloaded {len(downloaded)} new episode(s)"
                else:
                    result = "No new episodes found"
                if args.once:
                    _write_watch_status(f"Watching all feeds. {result}.", live)
                    return 0
                next_check = check_started + args.interval
                wait_seconds = max(0, next_check - time.monotonic())
                _write_watch_status(f"Watching all feeds. {result}. Next check in {wait_seconds:.0f} seconds.", live)
                _wait_for_watch_check(wait_seconds, live)
    except KeyboardInterrupt:
        console.print("Watch stopped.")
        return 0


def _wait_for_watch_check(wait_seconds: float, live: Live) -> None:
    if wait_seconds <= 0:
        return
    deadline = time.monotonic() + wait_seconds
    while True:
        remaining = max(0, deadline - time.monotonic())
        if remaining > 10:
            time.sleep(min(remaining - 10, 0.25))
            continue
        if remaining <= 0:
            break
        _write_watch_status(f"Watching all feeds. Next check in {int(remaining + 0.999)} seconds...", live)
        time.sleep(min(0.25, remaining))
    _write_watch_status("Watching all feeds. Refreshing feeds now.", live)


def _set_catch_up(storage: PodcastStorage, feed: dict[str, object]) -> None:
    feed_id = int(feed["id"])
    feed_title = str(feed["title"])
    if bool(feed.get("catch_up", False)):
        storage.set_feed_catch_up(feed_id, False)
        console.print(f"Catch-up mode disabled for '{feed_title}'.")
        return
    if not _confirm_catch_up(feed_title):
        console.print("Catch-up mode cancelled.")
        return
    storage.set_feed_catch_up(feed_id, True)
    new_count = storage.refresh_feed(feed_id, limit=None)
    console.print(f"Catch-up mode enabled for '{feed_title}'. Added {new_count} archive episode(s).")


def _interactive_menu() -> int:
    storage = ensure_storage()
    actions = ["Download newest episodes", "Set download count", "Set download filter", "View episodes", "Toggle priority", "Refresh feed", "Remove feed", "Enable catch-up mode"]
    selected_feed = 0

    while True:
        feeds = storage.list_feeds()
        selected_feed = min(selected_feed, len(feeds) + 1)

        os.system("cls")
        console.print("[bold]Podcast Catcher[/bold]")
        console.print("Use arrow keys to choose a podcast. Press Enter for actions; q or Esc to exit.\n")
        for index, feed in enumerate(feeds):
            marker = ">" if index == selected_feed else " "
            priority = " ★" if feed["priority"] else ""
            console.print(f"{marker} {feed['title']}{priority}")
        marker = ">" if selected_feed == len(feeds) else " "
        console.print(f"{marker} + Add podcast")
        marker = ">" if selected_feed == len(feeds) + 1 else " "
        console.print(f"{marker} Watch all feeds")

        key = msvcrt.getwch()
        if key == "\x03":
            raise KeyboardInterrupt
        if key in {"q", "Q", "\x1b"}:
            return 0
        if key in {"\x00", "\xe0"}:
            key = msvcrt.getwch()
            if key == "H":
                selected_feed = (selected_feed - 1) % (len(feeds) + 2)
            elif key == "P":
                selected_feed = (selected_feed + 1) % (len(feeds) + 2)
            continue
        if key != "\r":
            continue

        if selected_feed == len(feeds):
            url = input("RSS feed URL (blank to cancel): ").strip()
            if url:
                name = input("Podcast name (optional): ").strip() or None
                handle_add(argparse.Namespace(url=url, name=name, priority=False))
                input("\nPress Enter to continue...")
            continue

        if selected_feed == len(feeds) + 1:
            interval_text = input("Watch interval in seconds [900]: ").strip()
            try:
                interval = float(interval_text) if interval_text else 900
            except ValueError:
                interval = 0
            if interval <= 0:
                console.print("Watch interval must be greater than 0 seconds.")
            else:
                console.print("Watching all feeds. Press Ctrl+C to return to the menu.")
                handle_watch(argparse.Namespace(interval=interval, destination="./downloads", once=False))
                input("\nPress Enter to continue...")
            continue

        feed_id = int(feeds[selected_feed]["id"])
        action_index = 0
        while True:
            os.system("cls")
            console.print(f"[bold]{feeds[selected_feed]['title']}[/bold]\n")
            for index, action in enumerate(actions):
                marker = ">" if index == action_index else " "
                console.print(f"{marker} {action}")
            console.print("\nPress Esc to go back.")

            key = msvcrt.getwch()
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x1b":
                break
            if key in {"\x00", "\xe0"}:
                key = msvcrt.getwch()
                if key == "H":
                    action_index = (action_index - 1) % len(actions)
                elif key == "P":
                    action_index = (action_index + 1) % len(actions)
                continue
            if key != "\r":
                continue

            if action_index == 0:
                count = int(feeds[selected_feed].get("download_count", 3))
                handle_download(argparse.Namespace(feed_id=feed_id, episode_index=None, destination="./downloads", count=count))
            elif action_index == 1:
                count_text = input(f"Number of newest episodes [{feeds[selected_feed].get('download_count', 3)}]: ").strip()
                try:
                    count = int(count_text) if count_text else int(feeds[selected_feed].get("download_count", 3))
                except ValueError:
                    count = 0
                    console.print("Count must be an integer.")
                if count == 0:
                    pass
                elif count < 1:
                    console.print("Count must be at least 1.")
                else:
                    storage.set_feed_download_count(feed_id, count)
                    console.print(f"Download count set to {count} for '{feeds[selected_feed]['title']}'.")
            elif action_index == 2:
                filters = [("all", "Download all episodes"), ("skip_played", "Skip played episodes"), ("skip_archived", "Skip archived episodes"), ("skip_either", "Skip played or archived episodes")]
                current = feeds[selected_feed].get("download_filter", "all")
                for index, (value, label) in enumerate(filters):
                    console.print(f"{index + 1}. {label}{' (current)' if value == current else ''}")
                choice = input("Select filter [1-4, blank to cancel]: ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(filters):
                    value, label = filters[int(choice) - 1]
                    storage.set_feed_download_filter(feed_id, value)
                    console.print(f"Download filter set to: {label}.")
            elif action_index == 3:
                _view_feed_episodes(storage, feed_id)
            elif action_index == 4:
                handle_toggle(argparse.Namespace(feed_id=feed_id))
            elif action_index == 5:
                handle_refresh(argparse.Namespace(feed_id=feed_id))
            elif action_index == 6:
                handle_remove(argparse.Namespace(feed_id=feed_id))
            else:
                _set_catch_up(storage, feeds[selected_feed])
            input("\nPress Enter to continue...")
            break


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args in [["help"], ["-help"], ["--help"]]:
        raw_args = ["--help"]
    args = parser.parse_args(raw_args)
    warning = inspect_status(ensure_storage())
    if warning:
        console.print(f"[yellow]Status check: {warning}.[/yellow]")
    if not hasattr(args, "func"):
        if argv is not None and len(argv) > 0:
            parser.print_help()
            return 0
        try:
            result = _interactive_menu()
            export_status(ensure_storage())
            return result
        except KeyboardInterrupt:
            export_status(ensure_storage())
            console.print("Exiting.")
            return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
