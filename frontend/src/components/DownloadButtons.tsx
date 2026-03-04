import type { DownloadFormat, DownloadMode } from '../types'

interface DownloadButtonsProps {
  isVideo: boolean
  mode: DownloadMode
  supportsMp3: boolean
  downloadingKey: string | null
  itemIndex: number
  onDownload: (format: DownloadFormat, itemIndex: number) => void
}

function formatLabel(format: DownloadFormat): string {
  if (format === 'jpg') {
    return 'Image'
  }
  return format.toUpperCase()
}

function buttonKey(format: DownloadFormat, itemIndex: number): string {
  return `${itemIndex}:${format}`
}

function buttonLabel(format: DownloadFormat, isLoading: boolean): string {
  if (isLoading) {
    return `Downloading ${formatLabel(format)}...`
  }
  if (format === 'mp4') {
    return 'Download MP4'
  }
  if (format === 'mp3') {
    return 'Download MP3'
  }
  return 'Download Image'
}

function videoButtons(isBusy: boolean, supportsMp3: boolean, downloadingKey: string | null, itemIndex: number, onDownload: (format: DownloadFormat, itemIndex: number) => void) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <button
        type="button"
        disabled={isBusy}
        onClick={() => onDownload('mp4', itemIndex)}
        className="focus-ring rounded-xl bg-ig-gradient px-4 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {buttonLabel('mp4', downloadingKey === buttonKey('mp4', itemIndex))}
      </button>

      {supportsMp3 ? (
        <button
          type="button"
          disabled={isBusy}
          onClick={() => onDownload('mp3', itemIndex)}
          className="focus-ring rounded-xl border border-white/15 bg-ink-850 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-neon-pink/50 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {buttonLabel('mp3', downloadingKey === buttonKey('mp3', itemIndex))}
        </button>
      ) : null}
    </div>
  )
}

function imageButton(isBusy: boolean, downloadingKey: string | null, itemIndex: number, onDownload: (format: DownloadFormat, itemIndex: number) => void) {
  return (
    <button
      type="button"
      disabled={isBusy}
      onClick={() => onDownload('jpg', itemIndex)}
      className="focus-ring rounded-xl border border-white/15 bg-ink-850 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:border-neon-pink/50 disabled:cursor-not-allowed disabled:opacity-70"
    >
      {buttonLabel('jpg', downloadingKey === buttonKey('jpg', itemIndex))}
    </button>
  )
}

export function DownloadButtons({ isVideo, mode, supportsMp3, downloadingKey, itemIndex, onDownload }: DownloadButtonsProps) {
  const isBusy = Boolean(downloadingKey)

  return (
    <div className="space-y-3">
      {mode === 'photo' ? (
        <div className="space-y-2">
          {imageButton(isBusy, downloadingKey, itemIndex, onDownload)}
          <p className="text-xs text-slate-500">If preview is missing, download can still succeed.</p>
        </div>
      ) : null}

      {mode === 'reel' || mode === 'igtv' ? (
        isVideo ? (
          videoButtons(isBusy, supportsMp3, downloadingKey, itemIndex, onDownload)
        ) : (
          <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-400">This item is not a video.</p>
        )
      ) : null}

      {mode === 'story' || mode === 'carousel' ? (
        isVideo ? (
          videoButtons(isBusy, supportsMp3, downloadingKey, itemIndex, onDownload)
        ) : (
          imageButton(isBusy, downloadingKey, itemIndex, onDownload)
        )
      ) : null}

      {!supportsMp3 && (mode === 'reel' || mode === 'igtv' || mode === 'story' || mode === 'carousel') ? (
        <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-400">MP3 conversion is unavailable on this deployment.</p>
      ) : null}
    </div>
  )
}
