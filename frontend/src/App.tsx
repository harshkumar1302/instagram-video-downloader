import { useEffect, useMemo, useState } from 'react'
import { ApiClientError, downloadMedia, fetchInfo, healthCheck } from './api'
import { ProgressBar } from './components/ProgressBar'
import { ResultCard } from './components/ResultCard'
import { MediaModeToggle } from './components/MediaModeToggle'
import { ServerStatus } from './components/ServerStatus'
import { ToastStatus } from './components/ToastStatus'
import { UrlInputCard } from './components/UrlInputCard'
import type { DownloadFormat, DownloadMode, InfoResponse, MediaItem, ToastState, UiState } from './types'

const INSTAGRAM_URL_PATTERN = /instagram\.com\/(p|reel|reels|stories|tv)\//i
const MODE_LABEL: Record<DownloadMode, string> = {
  photo: 'Photo',
  reel: 'Reel',
  story: 'Story',
  igtv: 'IGTV',
  carousel: 'Carousel',
}

const MODE_HINT: Record<DownloadMode, string> = {
  photo: 'Use /p/... links for photo posts.',
  reel: 'Use /reel/... or /reels/... links.',
  story: 'Use /stories/... links.',
  igtv: 'Use /tv/... links.',
  carousel: 'Use /p/... links with multiple items.',
}

const MODE_PLACEHOLDER: Record<DownloadMode, string> = {
  photo: 'https://www.instagram.com/p/...',
  reel: 'https://www.instagram.com/reel/...',
  story: 'https://www.instagram.com/stories/...',
  igtv: 'https://www.instagram.com/tv/...',
  carousel: 'https://www.instagram.com/p/...',
}

function getUrlPathType(url: string): 'p' | 'reel' | 'reels' | 'stories' | 'tv' | null {
  const match = url.match(/instagram\.com\/([^/?#]+)/i)
  if (!match?.[1]) {
    return null
  }
  const segment = match[1].toLowerCase()
  if (segment === 'p' || segment === 'reel' || segment === 'reels' || segment === 'stories' || segment === 'tv') {
    return segment
  }
  return null
}

function isModeCompatibleWithUrl(mode: DownloadMode, url: string): boolean {
  const pathType = getUrlPathType(url)
  if (!pathType) {
    return false
  }
  if (mode === 'photo' || mode === 'carousel') {
    return pathType === 'p'
  }
  if (mode === 'reel') {
    return pathType === 'reel' || pathType === 'reels'
  }
  if (mode === 'story') {
    return pathType === 'stories'
  }
  return pathType === 'tv'
}

function toMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'Unexpected error occurred.'
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

function getItems(info: InfoResponse): MediaItem[] {
  if (Array.isArray(info.items) && info.items.length > 0) {
    return info.items
  }

  return [
    {
      id: info.id,
      title: info.title,
      description: info.description,
      uploader: info.uploader,
      uploader_id: info.uploader_id,
      duration: info.duration,
      width: info.width,
      height: info.height,
      filesize_approx: info.filesize_approx,
      like_count: info.like_count,
      comment_count: info.comment_count,
      thumbnail: info.thumbnail,
      is_video: info.is_video,
      ext: info.ext,
      media_kind: info.media_kind,
      item_index: info.item_index ?? 0,
    },
  ]
}

export default function App() {
  const [uiState, setUiState] = useState<UiState>('idle')
  const [serverStatus, setServerStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [urlInput, setUrlInput] = useState('')
  const [activeUrl, setActiveUrl] = useState('')
  const [info, setInfo] = useState<InfoResponse | null>(null)
  const [mode, setMode] = useState<DownloadMode>('photo')
  const [supportsMp3, setSupportsMp3] = useState(true)
  const [toast, setToast] = useState<ToastState | null>(null)
  const [progress, setProgress] = useState<{ visible: boolean; percent: number; label: string }>({
    visible: false,
    percent: 0,
    label: '',
  })
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)

  const isBusy = useMemo(() => uiState === 'fetchingInfo' || uiState === 'validating' || uiState === 'downloading', [uiState])

  useEffect(() => {
    let cancelled = false

    const runHealthCheck = async () => {
      try {
        const health = await healthCheck()
        if (!cancelled) {
          setServerStatus('online')
          setSupportsMp3(Boolean(health.supports_mp3 ?? true))
        }
      } catch {
        if (!cancelled) {
          setServerStatus('offline')
        }
      }
    }

    void runHealthCheck()

    return () => {
      cancelled = true
    }
  }, [])

  const hideProgressSoon = (delayMs = 450) => {
    window.setTimeout(() => {
      setProgress((current) => ({ ...current, visible: false }))
    }, delayMs)
  }

  const handleGrab = async () => {
    const normalized = urlInput.trim()

    setToast(null)
    setUiState('validating')
    setProgress({ visible: true, percent: 12, label: 'Validating URL...' })

    if (!normalized || !INSTAGRAM_URL_PATTERN.test(normalized)) {
      setUiState('error')
      setInfo(null)
      setToast({
        type: 'error',
        message: 'Please enter a valid Instagram post, reel, story, or TV URL.',
      })
      setProgress({ visible: false, percent: 0, label: '' })
      return
    }

    setUiState('fetchingInfo')
    setProgress({ visible: true, percent: 38, label: 'Fetching metadata from Instagram...' })

    try {
      if (!isModeCompatibleWithUrl(mode, normalized)) {
        setUiState('error')
        setInfo(null)
        setToast({
          type: 'error',
          message: `${MODE_LABEL[mode]} mode does not match this URL. ${MODE_HINT[mode]}`,
        })
        setProgress({ visible: false, percent: 0, label: '' })
        return
      }

      const payload = await fetchInfo(normalized, mode)
      setProgress({ visible: true, percent: 84, label: 'Preparing download options...' })

      setInfo(payload)
      setActiveUrl(normalized)
      setUiState('ready')
      const items = getItems(payload)
      const videoCount = items.filter((item) => item.is_video).length
      const imageCount = items.filter((item) => !item.is_video).length
      if (mode === 'photo') {
        setToast({ type: 'success', message: `Ready. ${imageCount} photo item${imageCount > 1 ? 's' : ''} detected.` })
      } else if (mode === 'carousel') {
        setToast({ type: 'success', message: `Ready. ${items.length} carousel item${items.length > 1 ? 's' : ''} detected.` })
      } else if (mode === 'story') {
        setToast({ type: 'success', message: `Ready. ${items.length} story item${items.length > 1 ? 's' : ''} detected.` })
      } else {
        setToast({ type: 'success', message: `Ready. ${videoCount} video item${videoCount > 1 ? 's' : ''} detected.` })
      }

      setProgress({ visible: true, percent: 100, label: 'Done' })
      hideProgressSoon()
      setServerStatus('online')
    } catch (error) {
      setUiState('error')
      setInfo(null)
      setToast({ type: 'error', message: toMessage(error) })
      setProgress({ visible: false, percent: 0, label: '' })
      if (error instanceof TypeError) {
        setServerStatus('offline')
      }
    } finally {
      setUrlInput('')
    }
  }

  const handleDownload = async (format: DownloadFormat, itemIndex: number) => {
    if (!activeUrl) {
      return
    }

    const formatText = format === 'jpg' ? 'Image' : format.toUpperCase()
    const itemLabel = `Item ${itemIndex + 1}`
    const currentKey = `${itemIndex}:${format}`

    setUiState('downloading')
    setDownloadingKey(currentKey)
    setToast({ type: 'info', message: `Downloading ${formatText} (${itemLabel})...` })

    try {
      const payload = await downloadMedia(activeUrl, format, mode, itemIndex)
      triggerBrowserDownload(payload.blob, payload.filename)

      setUiState('success')
      setToast({ type: 'success', message: `${formatText} download complete for ${itemLabel}.` })
      setServerStatus('online')
      window.setTimeout(() => setUiState('ready'), 300)
    } catch (error) {
      setUiState('error')
      setToast({ type: 'error', message: toMessage(error) })
      if (error instanceof TypeError) {
        setServerStatus('offline')
      }
    } finally {
      setDownloadingKey(null)
    }
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden px-4 py-14 sm:px-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_0%,rgba(225,48,108,0.2),transparent_35%),radial-gradient(circle_at_100%_15%,rgba(131,58,180,0.15),transparent_40%)]" />

      <main className="relative mx-auto w-full max-w-2xl">
        <header className="mb-10 text-center animate-rise">
          <div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl bg-ig-gradient shadow-[0_10px_35px_rgba(225,48,108,0.4)]">
            <svg viewBox="0 0 24 24" className="h-8 w-8 fill-white" aria-hidden="true">
              <path d="M12 2.2c2.7 0 3 0 4.1.1 1 0 1.5.2 1.9.3.5.2.8.4 1.1.7.3.3.5.7.7 1.1.1.4.3.9.3 1.9 0 1.1.1 1.4.1 4.1s0 3-.1 4.1c0 1-.2 1.5-.3 1.9-.2.5-.4.8-.7 1.1-.3.3-.7.5-1.1.7-.4.1-.9.3-1.9.3-1.1 0-1.4.1-4.1.1s-3 0-4.1-.1c-1 0-1.5-.2-1.9-.3a3 3 0 0 1-1.1-.7 3 3 0 0 1-.7-1.1c-.1-.4-.3-.9-.3-1.9 0-1.1-.1-1.4-.1-4.1s0-3 .1-4.1c0-1 .2-1.5.3-1.9.2-.5.4-.8.7-1.1.3-.3.7-.5 1.1-.7.4-.1.9-.3 1.9-.3 1.1 0 1.4-.1 4.1-.1M12 0C9.3 0 8.9 0 7.9.1 6.8.1 6 .3 5.4.5c-.7.3-1.3.6-1.9 1.2C2.9 2.3 2.6 2.9 2.3 3.6c-.3.7-.5 1.4-.5 2.5C1.7 7.1 1.7 7.5 1.7 12s0 4.9.1 5.9c0 1.1.2 1.8.5 2.5.3.7.6 1.3 1.2 1.9.6.6 1.2.9 1.9 1.2.7.3 1.4.5 2.5.5 1 0 1.4.1 5.9.1s4.9 0 5.9-.1c1.1 0 1.8-.2 2.5-.5.7-.3 1.3-.6 1.9-1.2.6-.6.9-1.2 1.2-1.9.3-.7.5-1.4.5-2.5 0-1 .1-1.4.1-5.9s0-4.9-.1-5.9c0-1.1-.2-1.8-.5-2.5-.3-.7-.6-1.3-1.2-1.9C21.1 1.7 20.5 1.4 19.8 1.1 19.1.8 18.4.6 17.3.6 16.3.5 15.9.5 12.4.5z" />
            </svg>
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
            Insta<span className="grad-text">Grab</span>
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-400 sm:text-base">
            Select mode first, paste an Instagram URL, then download your result in one flow.
          </p>
        </header>

        <ServerStatus status={serverStatus} />
        <MediaModeToggle value={mode} onChange={setMode} disabled={isBusy} />
        <UrlInputCard
          value={urlInput}
          onChange={setUrlInput}
          onGrab={handleGrab}
          isBusy={isBusy}
          placeholder={MODE_PLACEHOLDER[mode]}
          hint={MODE_HINT[mode]}
        />

        <div className="mt-4 flex flex-wrap justify-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">instagram.com/reel/...</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">instagram.com/p/...</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1">instagram.com/stories/...</span>
        </div>

        <ProgressBar visible={progress.visible} percent={progress.percent} label={progress.label} />
        <ToastStatus toast={toast} />

        {info ? (
          <ResultCard
            info={info}
            mode={mode}
            supportsMp3={supportsMp3}
            downloadingKey={downloadingKey}
            onDownload={handleDownload}
          />
        ) : null}

        <footer className="mt-12 pb-6 text-center text-xs leading-6 text-slate-500">
          InstaGrab uses yt-dlp under your local environment. Download only content you have permission to use.
        </footer>
      </main>
    </div>
  )
}
