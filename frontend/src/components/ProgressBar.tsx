interface ProgressBarProps {
  visible: boolean
  percent: number
  label: string
}

export function ProgressBar({ visible, percent, label }: ProgressBarProps) {
  if (!visible) {
    return null
  }

  return (
    <section className="card mt-5 animate-rise p-4">
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-slate-400">
        <span>{label}</span>
        <span>{Math.min(100, Math.max(0, Math.round(percent)))}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-ig-gradient transition-[width] duration-500 ease-out"
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
    </section>
  )
}
