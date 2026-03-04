import type { ToastState } from '../types'

interface ToastStatusProps {
  toast: ToastState | null
}

const TOAST_STYLE: Record<ToastState['type'], string> = {
  success: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
  info: 'border-neon-pink/30 bg-neon-pink/10 text-pink-300',
}

export function ToastStatus({ toast }: ToastStatusProps) {
  if (!toast) {
    return null
  }

  return <section className={`mt-5 animate-rise rounded-xl border px-4 py-3 text-sm font-medium ${TOAST_STYLE[toast.type]}`}>{toast.message}</section>
}
