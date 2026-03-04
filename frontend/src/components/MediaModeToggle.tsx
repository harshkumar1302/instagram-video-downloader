import type { DownloadMode } from '../types'

interface MediaModeToggleProps {
  value: DownloadMode
  onChange: (mode: DownloadMode) => void
  disabled?: boolean
}

function ModeButton({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string
  active: boolean
  disabled: boolean
  onClick: () => void
}) {
  const baseClass = 'focus-ring rounded-xl px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] transition'
  const activeClass = active
    ? 'bg-ig-gradient text-white'
    : 'border border-white/15 bg-ink-850 text-slate-300 hover:border-neon-pink/45'

  return (
    <button type="button" onClick={onClick} disabled={disabled} className={`${baseClass} ${activeClass} disabled:cursor-not-allowed disabled:opacity-50`}>
      {label}
    </button>
  )
}

export function MediaModeToggle({ value, onChange, disabled = false }: MediaModeToggleProps) {
  const options: Array<{ mode: DownloadMode; label: string }> = [
    { mode: 'photo', label: 'Photo' },
    { mode: 'reel', label: 'Reel' },
    { mode: 'story', label: 'Story' },
    { mode: 'igtv', label: 'IGTV' },
    { mode: 'carousel', label: 'Carousel' },
  ]

  return (
    <section className="card mb-4 p-5 sm:p-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Download Mode</h2>
        <p className="text-xs text-slate-500">Select first, then paste URL</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {options.map((option) => (
          <ModeButton
            key={option.mode}
            label={option.label}
            active={value === option.mode}
            disabled={disabled}
            onClick={() => onChange(option.mode)}
          />
        ))}
      </div>
    </section>
  )
}
