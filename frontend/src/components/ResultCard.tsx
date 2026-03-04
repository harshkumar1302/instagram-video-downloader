import { useEffect, useState } from 'react'
import { DownloadButtons } from './DownloadButtons'
import type { DownloadFormat, DownloadMode, InfoResponse, MediaItem } from '../types'

interface ResultCardProps {
  info: InfoResponse
  onDownload: (format: DownloadFormat, itemIndex: number) => void
  downloadingKey: string | null
  mode: DownloadMode
  supportsMp3: boolean
}

function formatDuration(totalSeconds: number): string {
  if (!totalSeconds || totalSeconds <= 0) {
    return '0:00'
  }

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function formatCount(value: number): string {
  if (!value || value < 1_000) {
    return String(value || 0)
  }

  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`
  }

  return `${(value / 1_000).toFixed(1)}K`
}

function formatSize(bytes: number): string {
  if (!bytes) {
    return 'Unknown'
  }

  if (bytes >= 1_048_576) {
    return `${(bytes / 1_048_576).toFixed(1)} MB`
  }

  if (bytes >= 1_024) {
    return `${Math.round(bytes / 1_024)} KB`
  }

  return `${bytes} B`
}

function mediaBadge(item: MediaItem): string {
  switch (item.media_kind) {
    case 'story':
      return 'Story'
    case 'reel':
      return 'Reel'
    case 'tv':
      return 'IGTV'
    default:
      return item.is_video ? 'Video' : 'Photo'
  }
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
      preview_url: info.preview_url,
      is_video: info.is_video,
      ext: info.ext,
      media_kind: info.media_kind,
      item_index: info.item_index ?? 0,
    },
  ]
}

function filterItemsByMode(items: MediaItem[], mode: DownloadMode): MediaItem[] {
  if (mode === 'photo') {
    const firstImage = items.find((item) => !item.is_video)
    return firstImage ? [firstImage] : []
  }
  if (mode === 'reel' || mode === 'igtv') {
    return items.filter((item) => item.is_video)
  }
  if (mode === 'story' || mode === 'carousel') {
    return items
  }
  return items
}

function emptyMessageForMode(mode: DownloadMode): string {
  if (mode === 'photo') {
    return 'No photo item found for this URL.'
  }
  if (mode === 'reel') {
    return 'No reel video found for this URL.'
  }
  if (mode === 'story') {
    return 'No story items found for this URL.'
  }
  if (mode === 'igtv') {
    return 'No IGTV video found for this URL.'
  }
  return 'No carousel items found for this URL.'
}

export function ResultCard({ info, downloadingKey, onDownload, mode, supportsMp3 }: ResultCardProps) {
  const allItems = getItems(info)
  const visibleItems = filterItemsByMode(allItems, mode)
  const [brokenThumbs, setBrokenThumbs] = useState<Record<number, number>>({})

  useEffect(() => {
    setBrokenThumbs({})
  }, [info.id, info.item_count, mode])

  if (!visibleItems.length) {
    return (
      <section className="card mt-6 p-5 text-sm text-slate-300">
        {emptyMessageForMode(mode)}
      </section>
    )
  }

  return (
    <section className="mt-6 space-y-4 animate-rise">
      {visibleItems.map((item) => {
        const avatarLetter = (item.uploader?.[0] || '?').toUpperCase()
        const stats: string[] = []

        if (item.is_video && item.duration) {
          stats.push(`Duration ${formatDuration(item.duration)}`)
        }

        if (item.like_count) {
          stats.push(`${formatCount(item.like_count)} likes`)
        }

        if (item.comment_count) {
          stats.push(`${formatCount(item.comment_count)} comments`)
        }

        if (item.width && item.height) {
          stats.push(`${item.width}x${item.height}`)
        }

        if (item.filesize_approx) {
          stats.push(formatSize(item.filesize_approx))
        }

        return (
          <article key={`${item.item_index}-${item.id || 'item'}`} className="card overflow-hidden">
            <div className="relative flex aspect-[4/5] max-h-[360px] items-center justify-center bg-gradient-to-br from-ink-900 via-ink-850 to-ink-800">
              {(() => {
                const previewCandidates = Array.from(new Set([item.preview_url, item.thumbnail].filter(Boolean))) as string[]
                const failureStep = brokenThumbs[item.item_index] ?? 0
                const previewSrc = previewCandidates[failureStep]

                if (!previewSrc) {
                  return <div className="text-sm text-slate-400">No thumbnail available</div>
                }

                return (
                  <img
                    src={previewSrc}
                    alt="Instagram thumbnail"
                    className="h-full w-full object-cover"
                    onError={() =>
                      setBrokenThumbs((current) => ({
                        ...current,
                        [item.item_index]: failureStep + 1,
                      }))
                    }
                  />
                )
              })()}

              <span className="absolute left-3 top-3 rounded-md border border-white/20 bg-black/45 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-pink-200">
                {mediaBadge(item)}
              </span>
              <span className="absolute right-3 top-3 rounded-md border border-white/20 bg-black/45 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-200">
                Item {item.item_index + 1}
              </span>
            </div>

            <div className="space-y-5 p-5 sm:p-6">
              <header className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-full bg-ig-gradient text-sm font-semibold text-white">{avatarLetter}</div>
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold text-white">{item.uploader || 'Unknown'}</p>
                  <p className="truncate text-sm text-slate-400">{item.uploader_id ? `@${item.uploader_id}` : '@unknown'}</p>
                </div>
              </header>

              <div>
                <h3 className="mb-1 text-sm font-semibold uppercase tracking-[0.12em] text-slate-400">Caption</h3>
                <p className="max-h-24 overflow-hidden text-sm leading-6 text-slate-300">{item.description || item.title || 'No caption'}</p>
              </div>

              {stats.length ? (
                <ul className="flex flex-wrap gap-2 text-xs font-medium text-slate-300">
                  {stats.map((stat) => (
                    <li key={stat} className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5">
                      {stat}
                    </li>
                  ))}
                </ul>
              ) : null}

              <DownloadButtons
                isVideo={item.is_video}
                mode={mode}
                supportsMp3={supportsMp3}
                itemIndex={item.item_index}
                downloadingKey={downloadingKey}
                onDownload={onDownload}
              />
            </div>
          </article>
        )
      })}
    </section>
  )
}
