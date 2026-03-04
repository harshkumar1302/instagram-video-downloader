export type DownloadFormat = 'mp4' | 'mp3' | 'jpg'
export type DownloadMode = 'photo' | 'reel' | 'story' | 'igtv' | 'carousel'

export type UiState =
  | 'idle'
  | 'validating'
  | 'fetchingInfo'
  | 'ready'
  | 'downloading'
  | 'success'
  | 'error'

export type ToastType = 'success' | 'error' | 'info'

export interface ApiError {
  error: string
  code: string
}

export interface HealthResponse {
  ok: boolean
  service: string
  runtime?: 'local' | 'vercel'
  supports_mp3?: boolean
}

export interface InfoResponse {
  id: string
  title: string
  description: string
  uploader: string
  uploader_id: string
  duration: number
  width: number
  height: number
  filesize_approx: number
  like_count: number
  comment_count: number
  thumbnail: string
  is_video: boolean
  ext: string
  media_kind: 'reel' | 'story' | 'tv' | 'post'
  preview_url?: string
  item_index?: number
  requested_mode?: DownloadMode | null
  items: MediaItem[]
  item_count: number
}

export interface MediaItem {
  id: string
  title: string
  description: string
  uploader: string
  uploader_id: string
  duration: number
  width: number
  height: number
  filesize_approx: number
  like_count: number
  comment_count: number
  thumbnail: string
  is_video: boolean
  ext: string
  media_kind: 'reel' | 'story' | 'tv' | 'post'
  preview_url?: string
  item_index: number
}

export interface ToastState {
  message: string
  type: ToastType
}

export interface DownloadPayload {
  blob: Blob
  filename: string
}
