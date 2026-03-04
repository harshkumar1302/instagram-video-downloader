import type { ApiError, DownloadFormat, DownloadMode, DownloadPayload, HealthResponse, InfoResponse } from './types'

export class ApiClientError extends Error {
  readonly code: string
  readonly status: number

  constructor(message: string, code: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function parseApiError(response: Response): Promise<ApiClientError> {
  try {
    const payload = (await response.json()) as ApiError
    const message = payload.error || `Request failed with status ${response.status}`
    const code = payload.code || 'UNKNOWN_ERROR'
    return new ApiClientError(message, code, response.status)
  } catch {
    return new ApiClientError(`Request failed with status ${response.status}`, 'UNKNOWN_ERROR', response.status)
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number,
  timeoutMessage: string,
): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (error) {
    if (isAbortError(error)) {
      throw new ApiClientError(timeoutMessage, 'TIMEOUT', 408)
    }
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

function parseFilename(dispositionHeader: string | null, fallback: string): string {
  if (!dispositionHeader) {
    return fallback
  }

  const utf8Match = dispositionHeader.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }

  const plainMatch = dispositionHeader.match(/filename=\"?([^\";]+)\"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }

  return fallback
}

export async function healthCheck(): Promise<HealthResponse> {
  const response = await fetchWithTimeout('/api/health', { method: 'GET' }, 7_000, 'Backend health check timed out.')
  if (!response.ok) {
    throw await parseApiError(response)
  }
  return (await response.json()) as HealthResponse
}

export async function fetchInfo(url: string, mode: DownloadMode): Promise<InfoResponse> {
  const response = await fetchWithTimeout(
    '/api/info',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, mode }),
    },
    35_000,
    'Fetching Instagram info timed out. Try again.',
  )

  if (!response.ok) {
    throw await parseApiError(response)
  }

  return (await response.json()) as InfoResponse
}

export async function downloadMedia(url: string, format: DownloadFormat, mode: DownloadMode, itemIndex?: number): Promise<DownloadPayload> {
  const response = await fetchWithTimeout(
    '/api/download',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, format, mode, item_index: itemIndex }),
    },
    130_000,
    'Download timed out. Try another item or URL.',
  )

  if (!response.ok) {
    throw await parseApiError(response)
  }

  const blob = await response.blob()
  const fallback = `instagram_download.${format}`
  const filename = parseFilename(response.headers.get('Content-Disposition'), fallback)

  return { blob, filename }
}
