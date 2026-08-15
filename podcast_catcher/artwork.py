from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import requests


def download_artwork(url: str, destination: str | Path) -> str:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    path.write_bytes(response.content)
    return str(path)


def _frame(frame_id: bytes, payload: bytes) -> bytes:
    return frame_id + len(payload).to_bytes(4, "big") + b"\x00\x00" + payload


def apply_artwork(file_path: str | Path, episode_title: str, podcast_name: str, image_path: str | Path) -> None:
    path = Path(file_path)
    image_path = Path(image_path)
    data = path.read_bytes()
    if not data.startswith(b"ID3"):
        return
    version = data[3]
    tag_size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9] if version == 4 else int.from_bytes(data[6:10], "big")
    audio = data[10 + tag_size:]
    image = image_path.read_bytes()
    mime = "image/png" if image[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    frames = [
        _frame(b"TIT2", b"\x01\xff\xfe" + episode_title.encode("utf-16-le") + b"\x00\x00"),
        _frame(b"TALB", b"\x01\xff\xfe" + podcast_name.encode("utf-16-le") + b"\x00\x00"),
        _frame(b"APIC", b"\x00" + mime.encode("ascii") + b"\x00\x03\x00" + image),
    ]
    body = b"".join(frames)
    header = b"ID3\x03\x00\x00" + len(body).to_bytes(4, "big")
    path.write_bytes(header + body + audio)


def artwork_filename(podcast_name: str, image_url: str) -> str:
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        suffix = ".jpg"
    safe_name = "".join(char if char.isalnum() else "-" for char in podcast_name).strip("-")
    return f"{safe_name.lower()}{suffix}"