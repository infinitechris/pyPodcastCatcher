# Device Dataset v1

`pyPodcastCatcher` exports a portable dataset for `esPod` with:

```text
device-export/
  manifest.json
  media/<podcast directory>/<episode filename>.mp3
```

The manifest is UTF-8 JSON with `schema_version: 1`. Each entry in `episodes`
contains the stable identity (`feed_url` and `episode_key`), display metadata,
the exact POSIX `relative_path`, file size, SHA-256 checksum, and playback state.

The device must identify episodes by `feed_url` plus `episode_key`, never by
SQLite row IDs or filenames. `episode_key` is the audio URL, falling back to
the episode link and then title. The `relative_path` value is authoritative.

The exporter includes only episodes whose local audio file exists. Artwork is
not copied separately; the MP3 may contain embedded ID3 APIC artwork.

The device should preserve unknown manifest fields, reject unsupported schema
versions, and write playback changes to its own state file rather than editing
the desktop SQLite database.