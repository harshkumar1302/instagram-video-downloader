from __future__ import annotations

import glob
import html as html_lib
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "instagrab_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

COOKIE_BROWSER = os.getenv("COOKIE_BROWSER", "chrome")
COOKIE_FILE = BASE_DIR / "cookies.txt"
IS_VERCEL = bool(os.getenv("VERCEL"))
AUTH_MODE = os.getenv("INSTAGRAB_AUTH_MODE", "none").lower()
DISABLE_MP3 = os.getenv("DISABLE_MP3", "1" if IS_VERCEL else "0").lower() in {"1", "true", "yes", "on"}
FFMPEG_LOCATION = os.getenv("FFMPEG_LOCATION", "").strip()
DOWNLOAD_TTL_SECONDS = int(os.getenv("DOWNLOAD_TTL_SECONDS", "3600"))
INFO_TIMEOUT_SECONDS = int(os.getenv("INFO_TIMEOUT_SECONDS", "30"))
DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "120"))
IMAGE_FETCH_TIMEOUT_SECONDS = int(os.getenv("IMAGE_FETCH_TIMEOUT_SECONDS", "8"))
IMAGE_CANDIDATE_LIMIT = int(os.getenv("IMAGE_CANDIDATE_LIMIT", "6"))
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "avif"}
NON_RECOVERABLE_IMAGE_CODES = {"INVALID_ITEM_INDEX", "AUTH_REQUIRED", "TIMEOUT", "YTDLP_NOT_FOUND"}

ALLOWED_INSTAGRAM_PATHS = {"p", "reel", "reels", "stories", "tv"}
TARGET_MODES = {"photo", "reel", "story", "igtv", "carousel"}

MODE_PATH_MAP = {
    "photo": {"p"},
    "carousel": {"p"},
    "reel": {"reel", "reels"},
    "story": {"stories"},
    "igtv": {"tv"},
}

app = Flask(__name__, static_folder=str(FRONTEND_DIST), static_url_path="")


@dataclass
class ApiException(Exception):
    message: str
    code: str
    status: int


def error_response(message: str, code: str, status: int) -> tuple[Response, int]:
    return jsonify({"error": message, "code": code}), status


def is_valid_instagram_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    if parsed.netloc.lower() not in {"instagram.com", "www.instagram.com"}:
        return False

    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return False

    return segments[0].lower() in ALLOWED_INSTAGRAM_PATHS


def infer_media_kind(value: str) -> str:
    parsed = urlparse(value)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return "post"

    mapping = {
        "reel": "reel",
        "reels": "reel",
        "stories": "story",
        "tv": "tv",
        "p": "post",
    }
    return mapping.get(segments[0].lower(), "post")


def get_primary_path_segment(value: str) -> str | None:
    parsed = urlparse(value.strip())
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return None
    return segments[0].lower()


def parse_target_mode(value: Any) -> str | None:
    if value is None:
        return None
    mode = str(value).strip().lower()
    if not mode:
        return None
    if mode not in TARGET_MODES:
        raise ApiException("mode must be one of: photo, reel, story, igtv, carousel.", "INVALID_MODE", 400)
    return mode


def validate_mode_for_url(mode: str | None, url: str) -> None:
    if mode is None:
        return
    segment = get_primary_path_segment(url)
    allowed_segments = MODE_PATH_MAP.get(mode, set())
    if segment not in allowed_segments:
        raise ApiException(
            f"Selected mode '{mode}' does not match this Instagram URL type.",
            "TYPE_MISMATCH",
            422,
        )


def filter_items_for_mode(items: list[dict[str, Any]], mode: str | None) -> list[dict[str, Any]]:
    if mode is None:
        return items

    if mode == "photo":
        image_items = [item for item in items if not bool(item.get("is_video"))]
        if not image_items:
            raise ApiException("Selected mode 'photo' requires an image post.", "TYPE_MISMATCH", 422)
        return [image_items[0]]

    if mode == "reel":
        video_items = [item for item in items if bool(item.get("is_video"))]
        if not video_items:
            raise ApiException("Selected mode 'reel' requires a video reel.", "TYPE_MISMATCH", 422)
        return video_items

    if mode == "igtv":
        video_items = [item for item in items if bool(item.get("is_video"))]
        if not video_items:
            raise ApiException("Selected mode 'igtv' requires a video IGTV post.", "TYPE_MISMATCH", 422)
        return video_items

    if mode == "story":
        if not items:
            raise ApiException("No story items found for this URL.", "TYPE_MISMATCH", 422)
        return items

    if mode == "carousel":
        if len(items) < 2:
            raise ApiException("Selected mode 'carousel' requires a multi-item post.", "TYPE_MISMATCH", 422)
        return items

    return items


def validate_mode_for_format(mode: str | None, fmt: str) -> None:
    if mode is None:
        return
    if mode == "photo" and fmt != "jpg":
        raise ApiException("Photo mode supports image download only.", "TYPE_MISMATCH", 422)
    if mode in {"reel", "igtv"} and fmt == "jpg":
        raise ApiException(f"{mode.upper()} mode supports video download only.", "TYPE_MISMATCH", 422)


def get_cookie_args() -> list[str]:
    # Browser cookie extraction is not available in serverless environments.
    if IS_VERCEL and AUTH_MODE in {"browser", "auto"} and not has_usable_cookie_file():
        return []

    if AUTH_MODE == "none":
        return []

    if AUTH_MODE == "file":
        return ["--cookies", str(COOKIE_FILE)] if has_usable_cookie_file() else []

    if AUTH_MODE == "browser":
        return ["--cookies-from-browser", COOKIE_BROWSER]

    if AUTH_MODE == "auto":
        if has_usable_cookie_file():
            return ["--cookies", str(COOKIE_FILE)]
        return ["--cookies-from-browser", COOKIE_BROWSER]

    # Invalid mode falls back to strict URL-only behavior.
    return []


def detect_ffmpeg_location() -> str | None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return None

    for candidate in [Path("/opt/homebrew/bin"), Path("/usr/local/bin")]:
        if (candidate / "ffmpeg").exists() and (candidate / "ffprobe").exists():
            return str(candidate)

    return None


AUTO_FFMPEG_LOCATION = detect_ffmpeg_location()


def get_ffmpeg_args() -> list[str]:
    if FFMPEG_LOCATION:
        return ["--ffmpeg-location", FFMPEG_LOCATION]

    if AUTO_FFMPEG_LOCATION:
        return ["--ffmpeg-location", AUTO_FFMPEG_LOCATION]

    return []


def has_usable_cookie_file() -> bool:
    if not COOKIE_FILE.exists() or not COOKIE_FILE.is_file():
        return False

    try:
        return COOKIE_FILE.stat().st_size > 0
    except OSError:
        return False


def clean_old_downloads() -> None:
    now = time.time()
    for path_str in glob.glob(str(DOWNLOAD_DIR / "*")):
        path = Path(path_str)
        try:
            if now - path.stat().st_mtime > DOWNLOAD_TTL_SECONDS:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
        except OSError:
            continue


def create_download_directory() -> Path:
    token = secrets.token_hex(8)
    target = DOWNLOAD_DIR / token
    target.mkdir(parents=True, exist_ok=True)
    return target


def parse_subprocess_failure(stderr: str, fallback_code: str, fallback_message: str) -> ApiException:
    lowered = stderr.lower()

    if "there is no video in this post" in lowered:
        return ApiException(
            "There is no video in this post.",
            "NO_VIDEO_IN_POST",
            422,
        )

    if "ffprobe and ffmpeg not found" in lowered or "ffmpeg not found" in lowered or "postprocessing" in lowered and "ffmpeg" in lowered:
        return ApiException(
            "FFmpeg is required for MP3 conversion. Install it (`brew install ffmpeg` on macOS) and restart the backend.",
            "FFMPEG_NOT_FOUND",
            500,
        )

    if any(token in lowered for token in ["login", "cookie", "sign in", "private"]):
        auth_hint = (
            "This Instagram URL requires login. URL-only mode supports publicly accessible posts only on Vercel."
            if IS_VERCEL
            else "This Instagram URL requires login. URL-only mode supports publicly accessible posts only."
        )
        return ApiException(
            auth_hint,
            "AUTH_REQUIRED",
            401,
        )

    message = stderr.strip().splitlines()[-1] if stderr.strip() else fallback_message
    return ApiException(message[:300], fallback_code, 400)


def resolve_yt_dlp_command() -> list[str]:
    binary_path = shutil.which("yt-dlp")
    if binary_path:
        return [binary_path]

    try:
        import yt_dlp  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ApiException(
            "yt-dlp is not installed. Run `npm run dev:backend` again to auto-install backend dependencies.",
            "YTDLP_NOT_FOUND",
            500,
        ) from exc

    return [sys.executable, "-m", "yt_dlp"]


def run_yt_dlp(args: list[str], timeout_seconds: int, failure_code: str, failure_message: str) -> str:
    command = [*resolve_yt_dlp_command(), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise ApiException(
            f"Operation timed out after {timeout_seconds} seconds.",
            "TIMEOUT",
            408,
        ) from exc
    except FileNotFoundError as exc:
        raise ApiException(
            "yt-dlp is not installed or not available on PATH.",
            "YTDLP_NOT_FOUND",
            500,
        ) from exc

    if result.returncode != 0:
        raise parse_subprocess_failure(result.stderr, failure_code, failure_message)

    return result.stdout


def parse_yt_json(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ApiException("No metadata returned by yt-dlp.", "INFO_EMPTY", 500)

    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ApiException("Failed to parse metadata from yt-dlp.", "INFO_PARSE_FAILED", 500) from exc

    return payload if isinstance(payload, dict) else {}


def get_media_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries_raw = payload.get("entries")
    if isinstance(entries_raw, list):
        entries = [entry for entry in entries_raw if isinstance(entry, dict)]
        if entries:
            return entries
    return [payload] if isinstance(payload, dict) and payload else []


def pick_entry_by_index(entries: list[dict[str, Any]], item_index: int | None) -> dict[str, Any] | None:
    if not entries:
        return None
    if item_index is None:
        return entries[0]
    if 0 <= item_index < len(entries):
        return entries[item_index]
    return None


def build_browser_headers(referer: str | None = None, accept: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    if accept:
        headers["Accept"] = accept
    if referer:
        headers["Referer"] = referer
    return headers


def fetch_page_html(source_url: str) -> str:
    request = Request(source_url, headers=build_browser_headers())
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ApiException("Failed to fetch page metadata from Instagram URL.", "PAGE_METADATA_FAILED", 400) from exc


def extract_meta_content(html_text: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return html_lib.unescape(match.group(1)).strip()
    return ""


def parse_uploader_from_og_title(og_title: str) -> str:
    title = og_title.strip()
    if not title:
        return "Unknown"

    marker = " on Instagram"
    if marker in title:
        return title.split(marker, 1)[0].strip() or "Unknown"

    return "Unknown"


def fetch_open_graph_metadata(source_url: str, html_text: str | None = None) -> dict[str, Any]:
    html_source = html_text if html_text is not None else fetch_page_html(source_url)

    og_title = extract_meta_content(html_source, "og:title")
    og_description = extract_meta_content(html_source, "og:description")
    og_image = extract_meta_content(html_source, "og:image")

    path_segments = [segment for segment in urlparse(source_url).path.split("/") if segment]
    post_id = path_segments[1] if len(path_segments) > 1 else ""

    title = og_title or "Instagram post"
    description = og_description or ""
    uploader = parse_uploader_from_og_title(og_title)

    return {
        "id": post_id,
        "title": title[:80],
        "description": description[:200],
        "uploader": uploader,
        "uploader_id": "",
        "duration": 0,
        "width": 0,
        "height": 0,
        "filesize_approx": 0,
        "like_count": 0,
        "comment_count": 0,
        "thumbnail": og_image,
        "is_video": False,
        "ext": "jpg",
        "media_kind": infer_media_kind(source_url),
    }


def normalize_item_from_og(source_url: str, item_index: int = 0, html_text: str | None = None) -> dict[str, Any]:
    fallback = fetch_open_graph_metadata(source_url, html_text=html_text)
    thumbnail = fallback.get("thumbnail")
    if isinstance(thumbnail, str):
        fallback["thumbnail"] = decode_escaped_url(thumbnail)
    return {
        **fallback,
        "item_index": item_index,
        "preview_url": build_preview_url(source_url, item_index),
    }


def decode_escaped_url(value: str) -> str:
    decoded = value.strip()
    replacements = {
        "\\/": "/",
        "\\u0026": "&",
        "\\u002F": "/",
        "\\u003D": "=",
        "\\u003d": "=",
        "\\u0025": "%",
        "\\x26": "&",
        "\\x3D": "=",
        "\\x3d": "=",
    }
    for source, target in replacements.items():
        decoded = decoded.replace(source, target)
    return html_lib.unescape(decoded)


def build_preview_url(source_url: str, item_index: int) -> str:
    query = urlencode(
        {
            "url": source_url,
            "item_index": max(item_index, 0),
        }
    )
    return f"/api/preview?{query}"


def is_probable_image_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()

    if any(token in path for token in [".mp4", ".m3u8", ".mpd"]):
        return False

    if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".avif"]):
        return True

    if any(token in query for token in ["dst-jpg", "jpeg", "jpg", "webp", "png", "heic", "heif", "avif", "format=jpg", "format=jpeg", "format=png", "format=webp"]):
        return True

    if any(token in host for token in ["cdninstagram", "fbcdn", "instagram"]):
        if any(token in query for token in ["video", "dash", "m3u8", "mp4"]):
            return False
        return any(token in path for token in ["/v/", "/vp/", "/t51.", "/scontent", "/e35"])

    return False


def is_image_bytes(payload: bytes) -> bool:
    if payload.startswith(b"\xff\xd8\xff"):
        return True
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if len(payload) > 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return True
    if len(payload) > 12 and payload[4:8] == b"ftyp" and payload[8:12] in {
        b"avif",
        b"avis",
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }:
        return True
    return False


def is_probable_html_bytes(payload: bytes) -> bool:
    sample = payload[:512].lstrip().lower()
    if sample.startswith(b"<!doctype html") or sample.startswith(b"<html"):
        return True
    if b"<head" in sample or b"<body" in sample or b"<title" in sample:
        return True
    return False


def add_image_candidate(candidates: list[str], seen: set[str], value: str | None) -> None:
    if not value:
        return
    decoded = decode_escaped_url(value)
    if not decoded or not is_probable_image_url(decoded):
        return
    if decoded in seen:
        return
    seen.add(decoded)
    candidates.append(decoded)


def collect_image_urls_from_payload(raw: dict[str, Any], limit: int | None = IMAGE_CANDIDATE_LIMIT) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for key in ["thumbnail", "display_url", "url", "image_url", "image"]:
        candidate = raw.get(key)
        if isinstance(candidate, str):
            add_image_candidate(candidates, seen, candidate)

    thumbnails = raw.get("thumbnails")
    if isinstance(thumbnails, list):
        for thumb in thumbnails:
            if isinstance(thumb, dict):
                candidate = thumb.get("url")
                if isinstance(candidate, str):
                    add_image_candidate(candidates, seen, candidate)

    formats = raw.get("formats")
    if isinstance(formats, list):
        for fmt in formats:
            if not isinstance(fmt, dict):
                continue
            ext = str(fmt.get("ext") or "").lower()
            vcodec = str(fmt.get("vcodec") or "").lower()
            acodec = str(fmt.get("acodec") or "").lower()
            fmt_url = fmt.get("url")
            if isinstance(fmt_url, str) and (ext in {"jpg", "jpeg", "png", "webp"} or (vcodec == "none" and acodec == "none")):
                add_image_candidate(candidates, seen, fmt_url)

    if limit is None:
        return candidates
    return candidates[: max(limit, 0)]


def collect_image_urls_from_html(html_text: str, limit: int | None = IMAGE_CANDIDATE_LIMIT) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    add_image_candidate(candidates, seen, extract_meta_content(html_text, "og:image"))

    patterns = [
        r'"display_url":"([^"]+)"',
        r'"thumbnail_src":"([^"]+)"',
        r'"image_url":"([^"]+)"',
        r'"src":"([^"]+)"',
        r'"url":"([^"]+)"',
        r"https?://[^\"'\\s<>]+",
        r"https?:\\\\/\\\\/[^\"'\\s<>]+",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, html_text, flags=re.IGNORECASE):
            value = match.group(1) if match.lastindex else match.group(0)
            add_image_candidate(candidates, seen, value)

    if limit is None:
        return candidates
    return candidates[: max(limit, 0)]


def download_image_from_url(image_url: str, source_url: str) -> tuple[bytes, str]:
    request = Request(
        image_url,
        headers=build_browser_headers(
            referer=source_url,
            accept="image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        ),
    )

    try:
        with urlopen(request, timeout=IMAGE_FETCH_TIMEOUT_SECONDS) as response:
            content_type = (response.headers.get_content_type() or "").lower()
            payload = response.read()
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ApiException("Failed to download image content from resolved URL.", "IMAGE_FETCH_FAILED", 400) from exc

    if not payload:
        raise ApiException("Image download returned empty content.", "IMAGE_EMPTY", 500)

    generic_binary_types = {"application/octet-stream", "binary/octet-stream", ""}
    if not content_type.startswith("image/"):
        if is_probable_html_bytes(payload):
            raise ApiException("Resolved URL returned HTML instead of image data.", "IMAGE_FETCH_FAILED", 400)
        if not is_image_bytes(payload):
            if not (content_type in generic_binary_types and is_probable_image_url(image_url)):
                raise ApiException("Resolved URL did not return image content.", "IMAGE_FETCH_FAILED", 400)

    return payload, content_type


def sanitize_filename(value: str, fallback: str = "instagram_media") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")
    return cleaned[:80] or fallback


def get_instagram_shortcode(value: str) -> str | None:
    parsed = urlparse(value.strip())
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return None
    if segments[0].lower() != "p":
        return None
    return segments[1].strip() or None


def build_instagram_media_endpoint_url(source_url: str, item_index: int | None = None) -> str | None:
    shortcode = get_instagram_shortcode(source_url)
    if not shortcode:
        return None
    endpoint = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    if item_index is not None and item_index >= 0:
        endpoint += f"&img_index={item_index + 1}"
    return endpoint


def infer_image_extension(content_type: str, source_url: str) -> str:
    extension_by_type = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/avif": "avif",
        "image/heic": "heic",
        "image/heif": "heif",
    }
    extension = extension_by_type.get(content_type)
    if extension:
        return extension

    suffix = Path(urlparse(source_url).path).suffix.lower().lstrip(".")
    if suffix == "jpeg":
        suffix = "jpg"
    return suffix if suffix in IMAGE_EXTENSIONS else "jpg"


def write_image_bytes_to_file(
    raw: dict[str, Any],
    download_dir: Path,
    image_bytes: bytes,
    content_type: str,
    source_url: str,
) -> tuple[Path, str]:
    extension = infer_image_extension(content_type, source_url)
    base_name = sanitize_filename(str(raw.get("title") or raw.get("id") or "instagram_image"), fallback="instagram_image")
    file_path = download_dir / f"{base_name}.{extension}"
    file_path.write_bytes(image_bytes)
    mimetype = content_type if content_type.startswith("image/") else (mimetypes.guess_type(file_path.name)[0] or "image/jpeg")
    return file_path, mimetype


def download_thumbnail_image(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    raw: dict[str, Any] = {}
    candidates: list[str] = []
    candidate_limit = IMAGE_CANDIDATE_LIMIT if item_index is None else max(IMAGE_CANDIDATE_LIMIT, item_index + 1)

    try:
        raw_stdout = run_yt_dlp(
            [
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                "--no-progress",
                *get_ffmpeg_args(),
                *get_cookie_args(),
                source_url,
            ],
            timeout_seconds=INFO_TIMEOUT_SECONDS,
            failure_code="IMAGE_INFO_FAILED",
            failure_message="Failed to fetch Instagram image metadata.",
        )
        payload = parse_yt_json(raw_stdout)
        entries = get_media_entries(payload)
        selected = pick_entry_by_index(entries, item_index)
        if selected is None:
            raise ApiException("Invalid carousel item index.", "INVALID_ITEM_INDEX", 400)

        raw = selected
        candidates.extend(collect_image_urls_from_payload(selected, limit=candidate_limit))
    except ApiException as exc:
        if exc.code in NON_RECOVERABLE_IMAGE_CODES:
            raise
        raw = {}

    page_html = ""
    if not candidates:
        try:
            page_html = fetch_page_html(source_url)
            html_candidates = collect_image_urls_from_html(page_html, limit=candidate_limit)
            if item_index is not None and html_candidates:
                if item_index < len(html_candidates):
                    candidates.append(html_candidates[item_index])
            else:
                candidates.extend(html_candidates)
            if not raw:
                raw = fetch_open_graph_metadata(source_url, html_text=page_html)
        except ApiException as exc:
            if exc.code == "INVALID_ITEM_INDEX":
                raise
            page_html = ""

    if not candidates:
        if item_index is not None and item_index > 0:
            raise ApiException("Invalid carousel item index.", "INVALID_ITEM_INDEX", 400)
        try:
            if not page_html:
                page_html = fetch_page_html(source_url)
            og_fallback = fetch_open_graph_metadata(source_url, html_text=page_html)
            thumbnail = str(og_fallback.get("thumbnail") or "").strip()
            if thumbnail:
                candidates.append(thumbnail)
            if not raw:
                raw = og_fallback
            else:
                for key in ["id", "title", "description", "uploader", "uploader_id"]:
                    if not raw.get(key) and og_fallback.get(key):
                        raw[key] = og_fallback[key]
        except ApiException:
            pass

    if not candidates:
        raise ApiException("Unable to resolve image URL from this post.", "IMAGE_NOT_AVAILABLE", 404)

    image_bytes = b""
    content_type = ""
    chosen_url = ""
    last_error: ApiException | None = None

    for candidate_url in candidates:
        try:
            image_bytes, content_type = download_image_from_url(candidate_url, source_url)
            chosen_url = candidate_url
            break
        except ApiException as exc:
            last_error = exc

    if not image_bytes:
        if last_error is not None and last_error.code in NON_RECOVERABLE_IMAGE_CODES:
            raise ApiException(last_error.message, last_error.code, last_error.status)
        raise ApiException(
            "Could not resolve a downloadable image for this item.",
            "IMAGE_NOT_AVAILABLE",
            404,
        )

    return write_image_bytes_to_file(raw, download_dir, image_bytes, content_type, chosen_url)


def normalize_info_payload(raw: dict[str, Any], source_url: str) -> dict[str, Any]:
    duration = raw.get("duration") or 0
    vcodec = str(raw.get("vcodec") or "")
    is_video = bool(duration and duration > 0) or (vcodec and vcodec.lower() != "none")

    title = raw.get("title") or (raw.get("description") or "Instagram post")[:80]
    description = (raw.get("description") or "").strip()

    raw_thumbnail = raw.get("thumbnail")
    thumbnail = decode_escaped_url(raw_thumbnail) if isinstance(raw_thumbnail, str) else ""

    return {
        "id": raw.get("id", ""),
        "title": title,
        "description": description[:200],
        "uploader": raw.get("uploader") or raw.get("channel") or "Unknown",
        "uploader_id": raw.get("uploader_id") or "",
        "duration": int(duration) if isinstance(duration, (int, float)) else 0,
        "width": raw.get("width") or 0,
        "height": raw.get("height") or 0,
        "filesize_approx": raw.get("filesize_approx") or 0,
        "like_count": raw.get("like_count") or 0,
        "comment_count": raw.get("comment_count") or 0,
        "thumbnail": thumbnail,
        "is_video": is_video,
        "ext": raw.get("ext") or ("mp4" if is_video else "jpg"),
        "media_kind": infer_media_kind(source_url),
    }


def normalize_media_item(raw: dict[str, Any], source_url: str, item_index: int) -> dict[str, Any]:
    item = normalize_info_payload(raw, source_url)
    if not item.get("thumbnail"):
        payload_candidates = collect_image_urls_from_payload(raw, limit=IMAGE_CANDIDATE_LIMIT)
        if payload_candidates:
            item["thumbnail"] = payload_candidates[0]
    item["item_index"] = item_index
    item["preview_url"] = build_preview_url(source_url, item_index)
    return item


def pick_downloaded_image_file(download_dir: Path) -> Path | None:
    files = sorted(download_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in files:
        if not candidate.is_file() or candidate.suffix == ".part":
            continue
        extension = candidate.suffix.lower().lstrip(".")
        if extension in IMAGE_EXTENSIONS:
            return candidate
    return None


def download_image_via_yt_dlp(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    output_template = str(download_dir / "%(title).50s.%(ext)s")
    playlist_item_value = str(item_index + 1) if item_index is not None else "1"
    args = [
        "-f",
        "best[ext=jpg]/best[ext=jpeg]/best[ext=png]/best[ext=webp]/best[ext=avif]/best[vcodec=none]/best",
        "--playlist-items",
        playlist_item_value,
        "--no-warnings",
        "--no-progress",
        "-o",
        output_template,
        *get_cookie_args(),
        source_url,
    ]

    run_yt_dlp(
        args,
        timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
        failure_code="IMAGE_DOWNLOAD_FAILED",
        failure_message="Failed to download Instagram image.",
    )

    image_file = pick_downloaded_image_file(download_dir)
    if image_file is None:
        raise ApiException("No image file was produced for this item.", "NO_IMAGE_IN_ITEM", 422)

    mimetype = mimetypes.guess_type(image_file.name)[0] or "image/jpeg"
    return image_file, mimetype


def get_thumbnail_urls_via_yt_dlp(source_url: str, item_index: int | None = None) -> list[str]:
    playlist_item_value = str(item_index + 1) if item_index is not None else "1"
    stdout = run_yt_dlp(
        [
            "--skip-download",
            "--print",
            "thumbnail",
            "--playlist-items",
            playlist_item_value,
            "--no-warnings",
            "--no-progress",
            *get_cookie_args(),
            source_url,
        ],
        timeout_seconds=INFO_TIMEOUT_SECONDS,
        failure_code="IMAGE_THUMB_URL_FAILED",
        failure_message="Failed to resolve thumbnail URL from Instagram item.",
    )

    urls: list[str] = []
    seen: set[str] = set()
    for line in stdout.splitlines():
        value = decode_escaped_url(line.strip())
        if not value or value.lower() == "na":
            continue
        if value in seen:
            continue
        seen.add(value)
        urls.append(value)
    return urls


def download_image_via_yt_thumbnail_urls(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    thumb_urls = get_thumbnail_urls_via_yt_dlp(source_url, item_index=item_index)
    if not thumb_urls:
        raise ApiException("No thumbnail URL was returned for this item.", "IMAGE_NOT_AVAILABLE", 404)

    last_error: ApiException | None = None
    for thumb_url in thumb_urls:
        try:
            image_bytes, content_type = download_image_from_url(thumb_url, source_url)
            return write_image_bytes_to_file({}, download_dir, image_bytes, content_type, thumb_url)
        except ApiException as exc:
            last_error = exc

    if last_error is not None and last_error.code in NON_RECOVERABLE_IMAGE_CODES:
        raise ApiException(last_error.message, last_error.code, last_error.status)
    raise ApiException("Could not download thumbnail image for this item.", "IMAGE_NOT_AVAILABLE", 404)


def download_image_via_media_endpoint(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    endpoint_url = build_instagram_media_endpoint_url(source_url, item_index=item_index)
    if not endpoint_url:
        raise ApiException("Media endpoint fallback is not available for this URL type.", "IMAGE_NOT_AVAILABLE", 404)
    image_bytes, content_type = download_image_from_url(endpoint_url, source_url)
    return write_image_bytes_to_file({}, download_dir, image_bytes, content_type, endpoint_url)


def download_written_thumbnail_via_yt_dlp(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    output_template = str(download_dir / "%(title).50s.%(ext)s")
    playlist_item_value = str(item_index + 1) if item_index is not None else "1"
    args = [
        "--skip-download",
        "--write-thumbnail",
        "--playlist-items",
        playlist_item_value,
        "--no-warnings",
        "--no-progress",
        "-o",
        output_template,
        *get_cookie_args(),
        source_url,
    ]

    run_yt_dlp(
        args,
        timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
        failure_code="IMAGE_THUMBNAIL_FAILED",
        failure_message="Failed to download Instagram thumbnail image.",
    )

    image_file = pick_downloaded_image_file(download_dir)
    if image_file is None:
        raise ApiException("No thumbnail image was produced for this item.", "IMAGE_NOT_AVAILABLE", 404)

    mimetype = mimetypes.guess_type(image_file.name)[0] or "image/jpeg"
    return image_file, mimetype


def resolve_image_file(source_url: str, download_dir: Path, item_index: int | None = None) -> tuple[Path, str]:
    fallback_chain = [
        download_image_via_yt_dlp,
        download_image_via_yt_thumbnail_urls,
        download_image_via_media_endpoint,
        download_written_thumbnail_via_yt_dlp,
        download_thumbnail_image,
    ]
    last_error: ApiException | None = None

    for downloader in fallback_chain:
        try:
            return downloader(source_url, download_dir, item_index=item_index)
        except ApiException as exc:
            if exc.code in NON_RECOVERABLE_IMAGE_CODES:
                raise
            last_error = exc
            continue

    if last_error and last_error.code in {"INVALID_ITEM_INDEX", "AUTH_REQUIRED", "TIMEOUT", "YTDLP_NOT_FOUND"}:
        raise ApiException(last_error.message, last_error.code, last_error.status)

    raise ApiException("Unable to resolve image URL from this post.", "IMAGE_NOT_AVAILABLE", 404)


def pick_downloaded_file(download_dir: Path, extension: str) -> Path | None:
    matching = sorted(download_dir.glob(f"*.{extension}"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matching:
        return matching[0]

    fallback = sorted(download_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in fallback:
        if candidate.suffix == ".part" or not candidate.is_file():
            continue
        return candidate

    return None


@app.get("/api/health")
def health() -> Response:
    return jsonify(
        {
            "ok": True,
            "service": "instagrab",
            "runtime": "vercel" if IS_VERCEL else "local",
            "supports_mp3": not DISABLE_MP3,
        }
    )


@app.post("/api/info")
def info() -> tuple[Response, int] | Response:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or "").strip()
    try:
        mode = parse_target_mode(payload.get("mode"))
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)

    if not is_valid_instagram_url(url):
        return error_response(
            "Invalid Instagram URL. Use instagram.com/(p|reel|stories|tv)/...",
            "INVALID_URL",
            400,
        )
    try:
        validate_mode_for_url(mode, url)
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)

    try:
        raw_stdout = run_yt_dlp(
            [
                "--dump-single-json",
                "--skip-download",
                "--no-warnings",
                "--no-progress",
                *get_ffmpeg_args(),
                *get_cookie_args(),
                url,
            ],
            timeout_seconds=INFO_TIMEOUT_SECONDS,
            failure_code="INFO_FETCH_FAILED",
            failure_message="Failed to fetch Instagram metadata.",
        )

        payload = parse_yt_json(raw_stdout)
        entries = get_media_entries(payload)
        if not entries:
            return error_response("No downloadable media entries found.", "INFO_EMPTY", 404)

        items = [normalize_media_item(entry, url, index) for index, entry in enumerate(entries)]

        if any(not item.get("thumbnail") for item in items):
            try:
                html_text = fetch_page_html(url)
                html_candidates = collect_image_urls_from_html(
                    html_text,
                    limit=max(IMAGE_CANDIDATE_LIMIT, len(items)),
                )
                if html_candidates:
                    for index, item in enumerate(items):
                        if not item.get("thumbnail") and index < len(html_candidates):
                            item["thumbnail"] = html_candidates[index]
                    if items and not items[0].get("thumbnail"):
                        items[0]["thumbnail"] = html_candidates[0]

                og_fallback = normalize_item_from_og(url, item_index=0, html_text=html_text)
                if items[0].get("uploader") == "Unknown":
                    items[0]["uploader"] = og_fallback.get("uploader") or "Unknown"
                if not items[0].get("description"):
                    items[0]["description"] = og_fallback.get("description") or ""
                if items[0].get("title") in {"", "Instagram post"}:
                    items[0]["title"] = og_fallback.get("title") or items[0].get("title")
                if not items[0].get("thumbnail"):
                    items[0]["thumbnail"] = og_fallback.get("thumbnail") or ""
            except ApiException:
                pass

        if any(not item.get("thumbnail") for item in items):
            for item in items:
                if item.get("thumbnail"):
                    continue
                endpoint_url = build_instagram_media_endpoint_url(url, item_index=item.get("item_index"))
                if endpoint_url:
                    item["thumbnail"] = endpoint_url

        items = filter_items_for_mode(items, mode)
        primary = dict(items[0])
        primary["items"] = items
        primary["item_count"] = len(items)
        primary["requested_mode"] = mode
        return jsonify(primary)
    except ApiException as exc:
        if exc.code == "NO_VIDEO_IN_POST":
            # Allow image-only posts to proceed in Image mode.
            if mode in {"reel", "igtv"}:
                return error_response("Selected mode requires video media.", "TYPE_MISMATCH", 422)
            try:
                fallback = normalize_item_from_og(url, item_index=0)
                fallback_items = filter_items_for_mode([fallback], mode)
                payload_out = dict(fallback_items[0])
                payload_out["items"] = fallback_items
                payload_out["item_count"] = len(fallback_items)
                payload_out["requested_mode"] = mode
                return jsonify(payload_out)
            except ApiException as fallback_exc:
                return error_response(fallback_exc.message, fallback_exc.code, fallback_exc.status)
        return error_response(exc.message, exc.code, exc.status)
    except Exception as exc:  # pragma: no cover
        return error_response(str(exc), "INTERNAL_ERROR", 500)


@app.post("/api/download")
def download() -> tuple[Response, int] | Response:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or "").strip()
    fmt = str(payload.get("format") or "mp4").lower()
    raw_item_index = payload.get("item_index")
    try:
        mode = parse_target_mode(payload.get("mode"))
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)

    item_index: int | None = None
    if raw_item_index is not None:
        try:
            item_index = int(raw_item_index)
        except (TypeError, ValueError):
            return error_response("item_index must be an integer.", "INVALID_ITEM_INDEX", 400)
        if item_index < 0:
            return error_response("item_index must be >= 0.", "INVALID_ITEM_INDEX", 400)

    if not is_valid_instagram_url(url):
        return error_response(
            "Invalid Instagram URL. Use instagram.com/(p|reel|stories|tv)/...",
            "INVALID_URL",
            400,
        )

    if fmt not in {"mp3", "mp4", "jpg"}:
        return error_response("format must be 'mp4', 'mp3', or 'jpg'.", "INVALID_FORMAT", 400)
    try:
        validate_mode_for_url(mode, url)
        validate_mode_for_format(mode, fmt)
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)

    if fmt == "mp3" and DISABLE_MP3:
        return error_response(
            "MP3 conversion is disabled on this deployment.",
            "MP3_DISABLED",
            422,
        )

    clean_old_downloads()
    download_dir = create_download_directory()

    try:
        if fmt == "jpg":
            file_path, mimetype = resolve_image_file(url, download_dir, item_index=item_index)
        else:
            output_template = str(download_dir / "%(title).50s.%(ext)s")
            playlist_item_value = str(item_index + 1) if item_index is not None else "1"

            if fmt == "mp3":
                args = [
                    "--extract-audio",
                    "--audio-format",
                    "mp3",
                    "--audio-quality",
                    "0",
                    "--playlist-items",
                    playlist_item_value,
                    "--no-warnings",
                    "--no-progress",
                    *get_ffmpeg_args(),
                    "-o",
                    output_template,
                    *get_cookie_args(),
                    url,
                ]
            else:
                args = [
                    "-f",
                    "best[ext=mp4]/best",
                    "--merge-output-format",
                    "mp4",
                    "--playlist-items",
                    playlist_item_value,
                    "--no-warnings",
                    "--no-progress",
                    *get_ffmpeg_args(),
                    "-o",
                    output_template,
                    *get_cookie_args(),
                    url,
                ]

            run_yt_dlp(
                args,
                timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS,
                failure_code="DOWNLOAD_FAILED",
                failure_message="Failed to download Instagram media.",
            )

            extension = "mp3" if fmt == "mp3" else "mp4"
            file_path = pick_downloaded_file(download_dir, extension)
            if file_path is None:
                return error_response(
                    "Download finished but output file was not found.",
                    "FILE_NOT_FOUND",
                    500,
                )

            if fmt == "mp3":
                mimetype = "audio/mpeg"
            else:
                mimetype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name,
            mimetype=mimetype,
            conditional=True,
        )
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)
    except Exception as exc:  # pragma: no cover
        return error_response(str(exc), "INTERNAL_ERROR", 500)


@app.get("/api/preview")
def preview() -> tuple[Response, int] | Response:
    url = str(request.args.get("url") or "").strip()
    raw_item_index = request.args.get("item_index")
    item_index: int | None = None

    if not is_valid_instagram_url(url):
        return error_response(
            "Invalid Instagram URL. Use instagram.com/(p|reel|stories|tv)/...",
            "INVALID_URL",
            400,
        )

    if raw_item_index is not None and raw_item_index != "":
        try:
            item_index = int(raw_item_index)
        except (TypeError, ValueError):
            return error_response("item_index must be an integer.", "INVALID_ITEM_INDEX", 400)
        if item_index < 0:
            return error_response("item_index must be >= 0.", "INVALID_ITEM_INDEX", 400)

    clean_old_downloads()
    download_dir = create_download_directory()

    try:
        file_path, mimetype = resolve_image_file(url, download_dir, item_index=item_index)
        response = send_file(
            file_path,
            as_attachment=False,
            mimetype=mimetype,
            conditional=True,
        )
        response.headers["Cache-Control"] = "public, max-age=300"
        return response
    except ApiException as exc:
        return error_response(exc.message, exc.code, exc.status)
    except Exception as exc:  # pragma: no cover
        return error_response(str(exc), "INTERNAL_ERROR", 500)


@app.get("/")
def frontend_index() -> Response:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")

    return jsonify(
        {
            "message": "Frontend build not found. Run `npm run build` from the project root, or use `npm run dev` for development.",
            "service": "instagrab",
        }
    )


@app.get("/<path:path>")
def frontend_assets(path: str) -> Response:
    if path.startswith("api/"):
        abort(404)

    asset_path = FRONTEND_DIST / path
    if asset_path.exists() and asset_path.is_file():
        return send_from_directory(FRONTEND_DIST, path)

    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return send_from_directory(FRONTEND_DIST, "index.html")

    abort(404)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug_enabled = os.getenv("FLASK_DEBUG", "0") == "1"

    print("\n" + "=" * 54)
    print("InstaGrab backend running")
    print(f"API: http://127.0.0.1:{port}/api/health")
    print(f"Frontend dist: {FRONTEND_DIST}")
    print(f"Runtime: {'vercel' if IS_VERCEL else 'local'}")
    print(f"FFmpeg location: {FFMPEG_LOCATION or AUTO_FFMPEG_LOCATION or 'PATH lookup'}")
    print(f"Auth mode: {AUTH_MODE}")
    print(f"MP3 enabled: {not DISABLE_MP3}")
    if AUTH_MODE == "file":
        print(f"Cookie source: {'backend/cookies.txt' if has_usable_cookie_file() else 'missing/empty cookies file'}")
    elif AUTH_MODE in {"browser", "auto"}:
        print(f"Cookie source: {'backend/cookies.txt' if has_usable_cookie_file() else f'browser ({COOKIE_BROWSER})'}")
    print("=" * 54 + "\n")

    app.run(host="0.0.0.0", port=port, debug=debug_enabled)
