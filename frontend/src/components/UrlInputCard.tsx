interface UrlInputCardProps {
  value: string
  onChange: (next: string) => void
  onGrab: () => void
  isBusy: boolean
  placeholder: string
  hint: string
}

export function UrlInputCard({ value, onChange, onGrab, isBusy, placeholder, hint }: UrlInputCardProps) {
  return (
    <section className="card p-5 sm:p-6">
      <label htmlFor="instagram-url" className="mb-2 block text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
        Instagram URL
      </label>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          id="instagram-url"
          type="url"
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={isBusy}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              onGrab()
            }
          }}
          placeholder={placeholder}
          className="focus-ring w-full rounded-xl border border-white/10 bg-ink-950/80 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500"
        />

        <button
          type="button"
          onClick={onGrab}
          disabled={isBusy}
          className="focus-ring rounded-xl bg-ig-gradient px-6 py-3 text-sm font-semibold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-65"
        >
          {isBusy ? 'Working...' : 'Grab'}
        </button>
      </div>

      <p className="mt-3 text-xs text-slate-500">{hint}</p>
    </section>
  )
}
