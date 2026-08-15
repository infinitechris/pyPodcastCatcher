from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import requests
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, DownloadColumn, TransferSpeedColumn

console = Console()


def _syncsafe_encode(value: int) -> bytes:
    return bytes(((value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F))


def _replace_id3_tags(file_path: Path, episode_title: str, podcast_name: str) -> None:
    data = file_path.read_bytes()
    if data[:3] != b"ID3" or data[3] not in (3, 4):
        return

    version = data[3]
    tag_size = int.from_bytes(data[6:10], "big") if version == 3 else (
        (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    )
    tag_end = 10 + tag_size
    position = 10
    frames: list[bytes] = []
    replacements = {b"TIT2": episode_title, b"TALB": podcast_name}
    replaced: set[bytes] = set()
    while position + 10 <= tag_end:
        frame_id = data[position:position + 4]
        if not frame_id.strip(b"\x00"):
            break
        raw_size = data[position + 4:position + 8]
        frame_size = int.from_bytes(raw_size, "big") if version == 3 else (
            (raw_size[0] << 21) | (raw_size[1] << 14) | (raw_size[2] << 7) | raw_size[3]
        )
        frame_end = position + 10 + frame_size
        if frame_end > tag_end:
            return
        if frame_id in replacements:
            payload = b"\x03" + replacements[frame_id].encode("utf-8")
            size = len(payload).to_bytes(4, "big") if version == 3 else _syncsafe_encode(len(payload))
            frames.append(frame_id + size + data[position + 8:position + 10] + payload)
            replaced.add(frame_id)
        else:
            frames.append(data[position:frame_end])
        position = frame_end

    for frame_id, value in replacements.items():
        if frame_id not in replaced:
            payload = b"\x03" + value.encode("utf-8")
            size = len(payload).to_bytes(4, "big") if version == 3 else _syncsafe_encode(len(payload))
            frames.append(frame_id + size + b"\x00\x00" + payload)

    new_tag_body = b"".join(frames)
    new_tag_size = max(tag_size, len(new_tag_body))
    padding = new_tag_size - len(new_tag_body)
    header = data[:6] + (_syncsafe_encode(new_tag_size) if version == 4 else new_tag_size.to_bytes(4, "big"))
    file_path.write_bytes(header + new_tag_body + (b"\x00" * padding) + data[tag_end:])


def _replace_id3_artwork(file_path: Path, image_data: bytes, mime_type: str) -> None:
    data = file_path.read_bytes()
    if data[:3] != b"ID3" or data[3] not in (3, 4):
        return
    version = data[3]
    tag_size = int.from_bytes(data[6:10], "big") if version == 3 else ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    tag_end, position = 10 + tag_size, 10
    frames: list[bytes] = []
    while position + 10 <= tag_end:
        frame_id = data[position:position + 4]
        if not frame_id.strip(b"\x00"):
            break
        raw_size = data[position + 4:position + 8]
        frame_size = int.from_bytes(raw_size, "big") if version == 3 else ((raw_size[0] << 21) | (raw_size[1] << 14) | (raw_size[2] << 7) | raw_size[3])
        frame_end = position + 10 + frame_size
        if frame_end > tag_end:
            return
        if frame_id != b"APIC":
            frames.append(data[position:frame_end])
        position = frame_end
    payload = b"\x00" + mime_type.encode("ascii", errors="ignore") + b"\x00\x03\x00" + image_data
    size = len(payload).to_bytes(4, "big") if version == 3 else _syncsafe_encode(len(payload))
    frames.append(b"APIC" + size + b"\x00\x00" + payload)
    body = b"".join(frames)
    new_size = max(tag_size, len(body))
    header = data[:6] + (_syncsafe_encode(new_size) if version == 4 else new_size.to_bytes(4, "big"))
    file_path.write_bytes(header + body + (b"\x00" * (new_size - len(body))) + data[tag_end:])


def _normalize_mp3_tags(file_path: Path, episode_title: str, podcast_name: str, artwork: tuple[bytes, str] | None = None) -> None:
    if file_path.suffix.lower() != ".mp3":
        return
    try:
        from mutagen.id3 import APIC, ID3, TALB, TIT2
        from mutagen.mp3 import HeaderNotFound
    except ImportError:
        _replace_id3_tags(file_path, episode_title, podcast_name)
        if artwork:
            _replace_id3_artwork(file_path, *artwork)
        return
    try:
        tags = ID3(file_path)
    except (HeaderNotFound, OSError):
        return
    tags.delall("TIT2")
    tags.add(TIT2(encoding=3, text=episode_title))
    tags.delall("TALB")
    tags.add(TALB(encoding=3, text=podcast_name))
    if artwork:
        image_data, mime_type = artwork
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=mime_type, type=3, desc="", data=image_data))
    tags.save(file_path)


def _safe_filename_from_url(url: str) -> str:
    parsed = urlsplit(url)
    candidate = parsed.path.split("/")[-1] if parsed.path else "download.bin"
    candidate = candidate.split("?")[0].split("#")[0]
    if not candidate:
        candidate = "download.bin"
    return candidate


def _safe_filename_from_title(title: str, url: str) -> str:
    cleaned_title = re.sub(r"['’.]", "", title.strip())
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", cleaned_title)
    cleaned = cleaned.strip("-")
    cleaned = cleaned.lower() or "episode"

    parsed = urlsplit(url)
    suffix = Path(parsed.path).suffix.lower() if parsed.path else ".mp3"
    if not suffix:
        suffix = ".mp3"
    return f"{cleaned}{suffix}"


def _safe_directory_name(value: str) -> str:
    cleaned = value.strip()
    cleaned = ''.join(ch if ch.isalnum() or ch in {' ', '-', '_'} else ' ' for ch in cleaned)
    cleaned = cleaned.replace('_', ' ')
    cleaned = ' '.join(cleaned.split())
    cleaned = cleaned.strip(' .-_/')
    return cleaned or "podcast"


def download_file(
    url: str,
    destination_dir: str | Path = "./downloads",
    *,
    priority: bool = False,
    podcast_name: str | None = None,
    force: bool = False,
    episode_title: str | None = None,
    artwork_url: str | None = None,
    show_progress: bool = True,
) -> str:
    destination = Path(destination_dir)
    if podcast_name:
        destination = destination / _safe_directory_name(podcast_name)
    destination.mkdir(parents=True, exist_ok=True)

    if episode_title:
        filename = _safe_filename_from_title(episode_title, url)
    else:
        filename = _safe_filename_from_url(url)
    if priority:
        stem, suffix = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = f"PRIORITY_{stem}{'.' + suffix if suffix else ''}"
    file_path = destination / filename

    if file_path.exists() and not force:
        raise FileExistsError(f"File already exists: {file_path}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    total_bytes = int(response.headers.get("Content-Length", 0)) or None
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
        transient=True,
    ) if show_progress else None
    if progress:
        progress.start()
        task_id = progress.add_task(f"Downloading {file_path.name}", total=total_bytes or 0)
    try:
        with file_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                handle.write(chunk)
                if progress:
                    if total_bytes:
                        progress.update(task_id, advance=len(chunk))
                    else:
                        progress.advance(task_id, 65536)
    finally:
        if progress:
            progress.stop()

    if episode_title and podcast_name:
        artwork = None
        if artwork_url:
            try:
                artwork_response = requests.get(artwork_url, timeout=30)
                artwork_response.raise_for_status()
                artwork = (artwork_response.content, artwork_response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0])
            except requests.RequestException:
                pass
        _normalize_mp3_tags(file_path, episode_title, podcast_name, artwork)

    return str(file_path)
