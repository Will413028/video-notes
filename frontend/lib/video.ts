export const DEMO_URL = 'fixture://learning-demo'

export type VideoInfo = {
  id: string
  title: string
  uploader: string
  duration_seconds: number
  source: string
  formats: { format_id: string; label: string; ext: string; has_audio: boolean; requires_merge: boolean }[]
}

function isVideoInfo(value: unknown): value is VideoInfo {
  if (typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return typeof record.id === 'string' && typeof record.title === 'string'
    && typeof record.uploader === 'string' && typeof record.source === 'string'
    && typeof record.duration_seconds === 'number'
    && Number.isFinite(record.duration_seconds) && record.duration_seconds >= 0
    && Array.isArray(record.formats) && record.formats.every(format =>
      typeof format === 'object' && format !== null && typeof format.format_id === 'string'
      && typeof format.label === 'string' && typeof format.ext === 'string'
      && typeof format.has_audio === 'boolean' && typeof format.requires_merge === 'boolean')
}

export async function parseVideo(url: string): Promise<VideoInfo> {
  const response = await fetch('/api/parse', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!response.ok) {
    if (response.status === 422) throw new Error('目前支援 YouTube 與 Bilibili，也可以點選「帶入範例」。')
    throw new Error('暫時無法解析，請稍後再試。')
  }
  const data: unknown = await response.json()
  if (!isVideoInfo(data)) throw new Error('影片資訊不完整，請稍後再試。')
  return data
}
