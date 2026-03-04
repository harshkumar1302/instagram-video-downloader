# InstaGrab

Production-oriented Instagram downloader monorepo.

- Frontend: React + TypeScript + Vite + Tailwind
- Backend: Flask + yt-dlp
- Deploy target: Vercel (single project)

## Important Notes

- `INSTAGRAB_AUTH_MODE=none` is the default. Public URLs only.
- MP3 conversion needs FFmpeg. For Vercel, MP3 is disabled by default (`DISABLE_MP3=1`).
- Browser cookie extraction is a local-only feature. It does not work on Vercel serverless runtime.

## Download Flow Mapping

1. Select mode first: `photo | reel | story | igtv | carousel`
2. Paste URL that matches the mode.
3. Frontend calls `POST /api/info` with `{ url, mode }`
4. Backend validates mode-url compatibility and resolves media items.
5. UI renders per-item preview cards.
6. Per item, click download:
   - video item: MP4 or MP3
   - photo item: JPG

Mode to URL mapping:

- `photo` -> `/p/...` (single image expected)
- `carousel` -> `/p/...` (multi-item expected)
- `reel` -> `/reel/...` or `/reels/...`
- `story` -> `/stories/...`
- `igtv` -> `/tv/...`

## Project Structure

```text
.
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── run_backend.sh
│   ├── run_backend_prod.sh
│   ├── server.py
│   └── wsgi.py
├── frontend/
│   ├── src/
│   └── ...
├── requirements.txt
├── server.py
├── vercel.json
└── package.json
```

## Local Development

### 1. Install Node deps

```bash
npm install
```

### 2. Run both backend + frontend

```bash
npm run dev
```

### 3. Open app

```text
http://127.0.0.1:5173
```

If port 5000 is busy:

```bash
PORT=5001 BACKEND_PORT=5001 npm run dev
```

## Local Production Run (No Flask Dev Server)

This uses Gunicorn, not Flask's development server.

```bash
npm run build
PORT=5000 npm run start
```

Open:

```text
http://127.0.0.1:5000
```

## API

### `GET /api/health`

```json
{
  "ok": true,
  "service": "instagrab",
  "runtime": "local",
  "supports_mp3": true
}
```

### `POST /api/info`

Request:

```json
{ "url": "https://www.instagram.com/p/...", "mode": "photo" }
```

### `POST /api/download`

Request:

```json
{ "url": "https://www.instagram.com/p/...", "mode": "photo", "format": "jpg", "item_index": 0 }
```

### `GET /api/preview`

Request:

```text
/api/preview?url=https%3A%2F%2Fwww.instagram.com%2Fp%2F...&item_index=0
```

This endpoint proxies image preview bytes, so thumbnails can still render even when direct Instagram CDN thumbnail URLs fail in the browser.

Formats:

- `mp4`
- `mp3` (if enabled)
- `jpg`

Errors use:

```json
{ "error": "...", "code": "..." }
```

## Vercel Deployment

### 1. Prerequisites

- Vercel account + CLI (`npm i -g vercel`) or GitHub integration.
- This repo includes:
  - `server.py` as Vercel Flask entrypoint
  - `vercel.json` with build + function config
  - root `requirements.txt` for Python dependencies
  - `npm run build:vercel` to publish frontend files into `public/`

### 2. Deploy

```bash
vercel
vercel --prod
```

### 3. Recommended Vercel Environment Variables

Set these in Project Settings -> Environment Variables:

- `INSTAGRAB_AUTH_MODE=none`
- `DISABLE_MP3=1`
- `INFO_TIMEOUT_SECONDS=30`
- `DOWNLOAD_TIMEOUT_SECONDS=120`

### 4. Post-deploy check

- `GET https://<your-domain>/api/health`
- Open app at `https://<your-domain>/`

## Environment Variables

See `backend/.env.example`.

Key values:

- `PORT`
- `FLASK_DEBUG`
- `INSTAGRAB_AUTH_MODE` (`none|browser|file|auto`)
- `COOKIE_BROWSER`
- `FFMPEG_LOCATION`
- `DISABLE_MP3`
- `INFO_TIMEOUT_SECONDS`
- `DOWNLOAD_TIMEOUT_SECONDS`
- `DOWNLOAD_TTL_SECONDS`
- `IMAGE_FETCH_TIMEOUT_SECONDS`
- `IMAGE_CANDIDATE_LIMIT`

## Troubleshooting

- `WARNING: This is a development server`: use `npm run start` for Gunicorn production runtime.
- `AUTH_REQUIRED`: URL is private/login-gated. URL-only mode cannot access it.
- `FFMPEG_NOT_FOUND`: install FFmpeg locally and restart backend.
- `MP3_DISABLED`: deployment has MP3 conversion disabled.
- `YTDLP_NOT_FOUND`: run backend bootstrap again (`npm run dev:backend` or `npm run start`).
- `TIMEOUT`: retry or increase timeout env vars carefully.
