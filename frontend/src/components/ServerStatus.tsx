interface ServerStatusProps {
  status: 'checking' | 'online' | 'offline'
}

const STYLES: Record<ServerStatusProps['status'], string> = {
  checking: 'border-white/15 bg-white/5 text-slate-300',
  online: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  offline: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
}

const LABELS: Record<ServerStatusProps['status'], string> = {
  checking: 'Checking backend connection...',
  online: 'Backend online and ready',
  offline: 'Backend offline. Run `npm run dev` in project root.',
}

export function ServerStatus({ status }: ServerStatusProps) {
  return (
    <div className={`mb-6 rounded-xl border px-4 py-3 text-sm font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </div>
  )
}
