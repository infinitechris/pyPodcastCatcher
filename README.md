# Podcast Catcher

Podcast Catcher is a lightweight command-line podcast manager for subscribing to RSS feeds, listing episodes, and downloading audio files into a local `downloads` directory.

## Features

- Add a podcast feed by URL
- Mark a podcast as priority during subscription with `--priority`
- Dynamically toggle priority on any feed after adding with the `toggle` command
- List saved feeds and episodes with visual priority indicators (★)
- Download a selected episode to `./downloads`
- Remove a subscribed feed with confirmation (defaults to no)
- Store feed and episode metadata in SQLite
- Automatically prefix priority downloads with `PRIORITY_` when the feed is flagged
- Cache podcast artwork from the RSS feed and embed it in downloaded MP3s
- Normalize MP3 title and album tags from RSS metadata
- Track persistent played and archived states for every episode
- Track partial playback position and duration for resume support
- Browse episodes in pages of 10 within the interactive podcast view
- Export episode state for device synchronization with a SHA1 integrity file

## Quick start

1. Create and activate a virtual environment if needed.
2. Install dependencies:

   ```bash
   python -m pip install -e .
   ```

3. Run the CLI:

   ```bash
   python -m podcast_catcher --help
   ```

## Example commands

```bash
python -m podcast_catcher add "https://example.com/feed.xml" --name "Example Podcast"
python -m podcast_catcher add "https://example.com/feed.xml" --name "Priority Podcast" --priority
python -m podcast_catcher list feeds
python -m podcast_catcher list episodes --feed-id 1
python -m podcast_catcher refresh
python -m podcast_catcher refresh 1
python -m podcast_catcher watch
python -m podcast_catcher watch --interval 300
python -m podcast_catcher watch --once
python -m podcast_catcher download
python -m podcast_catcher download 1
python -m podcast_catcher download --count 5
python -m podcast_catcher download 1 0 --destination ./downloads
python -m podcast_catcher toggle 1
python -m podcast_catcher toggle
python -m podcast_catcher remove 1
python -m podcast_catcher remove
```

### Interactive mode

Run `podcast_catcher` without a command to open the interactive podcast browser.

- Use Up and Down arrows to select a podcast.
- Press Enter to open its actions.
- Use Up and Down arrows to choose downloading, priority toggling, refreshing, or removal.
- Use `Set download count` to configure how many newest episodes that podcast downloads.
- `Download newest episodes` uses the saved per-podcast count, which defaults to 3.
- `Set download filter` can download all episodes, skip played episodes, skip archived episodes, or skip either state.
- Download filters apply to manual downloads, catch-up downloads, and autonomous watching.
- The intentionally buried `Enable catch-up mode` action switches that podcast to oldest-first downloading and may fetch its full available archive after confirmation.
- Press Enter to run the selected action.
- Press Esc to return to the podcast list or `q`/Esc to exit.
- Select `+ Add podcast` below the feeds to enter a new RSS URL and optional name.
- Select `Watch all feeds` below the feeds to start autonomous monitoring.
- Press Ctrl+C in any non-watcher TUI view to exit the application.

### Episode states

- Select `View episodes` inside an individual podcast to browse its episodes.
- The episode list displays `played` and `archived` states for every episode.
- The list shows up to 10 episodes at a time; select `MORE >` to view the next page.
- In an episode's action view, the controls show the current state and the state that will be applied, for example `Played: Off -> On`.
- Select `Played` or `Archived` to toggle that state.
- Episode states are stored permanently in SQLite and survive removing and re-adding the podcast.
- Partial playback is stored separately from completion: an episode can be `Played: Off` while retaining a resume position.

### Playback progress

- Playback position and duration are stored in seconds with a UTC update timestamp.
- The `played` flag represents completed playback; it is not set merely because an episode has a partial position.
- Device software can use `playback_position_seconds` and `duration_seconds` to resume an episode.
- `playback_updated_at` supports conflict resolution when desktop and device playback progress differ.

### Device status synchronization

- When the desktop TUI exits, it writes `downloads/podcast-status.json` and `downloads/podcast-status.sha1`.
- The JSON contains played and archived state keyed by feed URL and stable episode identity.
- Each episode entry also contains partial playback position, duration, and `*_updated_at` timestamps for device synchronization.
- On the next launch, a valid SHA1 check is silent.
- If the hash is invalid, Podcast Catcher compares the JSON content with the desktop database and reports whether they differ; it does not automatically import untrusted changes.
- A device app can update the JSON while the files are on the device, then return it for a later desktop comparison/import workflow.

### Download behavior

- `download` with no arguments downloads the 3 newest episodes from each feed.
- `download --count N` downloads the N newest episodes from each feed (default: 3).
- `download <feed_id>` downloads the N newest episodes from a specific feed.
- `download <feed_id> <episode_index>` downloads a specific episode by index.
- All episodes are sorted by published date with newest episodes first.
- **Feeds are automatically refreshed before downloading** to fetch latest episodes from their RSS feeds.
- Normal refreshes keep the newest requested window; explicit episode selection can fetch older feed entries.
- Downloaded MP3s use RSS episode titles for filenames and ID3 title tags.
- The album tag is set to the podcast name.
- Podcast artwork is embedded as an ID3v2.3 `APIC` frame for compatibility with KID3 and iTunes.

### Feed artwork and metadata

- `add` downloads one copy of the feed artwork into the local `artwork` directory.
- `scripts/apply_artwork.py` can reapply cached or freshly discovered artwork after other file processing.
- The script writes title, album, and cover-art tags without changing the audio stream.
- Apostrophes and periods are removed from generated filenames while other punctuation is normalized to hyphens.

### Add errors

- Feed URLs must be absolute `http://` or `https://` URLs.
- Invalid URLs, timeouts, connection failures, HTTP errors, and feeds with no episodes return a concise `Could not add feed: ...` message and exit with status `1`.
- Artwork download failures produce a warning; the feed can still be added without artwork.

### Refresh behavior

- `refresh` with no arguments refreshes all feeds to fetch latest episodes.
- `refresh <feed_id>` refreshes a specific feed.
- **Automatic refresh**: Feeds are refreshed in the background whenever you run `download` to ensure you always get the latest episodes.
- Refresh adds only new episodes; existing episodes are not duplicated.

### Autonomous watching

- `watch` checks all subscribed feeds every 900 seconds by default.
- Use `watch --interval SECONDS` to change the polling interval.
- Use `watch --once` to perform one check and exit, which is useful for scheduled tasks.
- Feed errors are ignored silently so one unavailable feed does not stop watching the others.
- Only episodes inserted during the current check are downloaded.
- Existing files are skipped and are never re-downloaded by the watcher.
- Stop a continuous watcher with Ctrl+C.
- Select `Watch all feeds` below the podcast list to start monitoring every subscribed feed; enter its interval and press Ctrl+C to return to the menu.

### Priority behavior

- If `--priority` is passed when subscribing, that feed is treated as a priority feed.
- Use the `toggle` command to enable/disable priority on a feed after it has been added.
- The `list feeds` command displays a star (★) next to priority feeds.
- Downloads from priority feeds are saved with a `PRIORITY_` prefix, for example:
  - `PRIORITY_episode-name.mp3`
- If priority is not enabled, the podcast is treated as normal and downloads keep their regular filename.

## Testing

```bash
python -m pytest
```

## Project scripts

```bash
python -m podcast_catcher
make test
make run
```

## License

This project is distributed under the MIT License.
