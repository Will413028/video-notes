'use client'

import { useEffect, useRef, useState } from 'react'

type Segment = { start: number; end: number; text: string }
type Transcript = {
  status: 'ready' | 'unavailable' | 'unsupported'
  tracks: { id: string; language: string; source: 'manual' | 'automatic' }[]
  selected: string | null
  segments: Segment[]
}

function isTranscript(data: unknown): data is Transcript {
  if (typeof data !== 'object' || data === null) return false
  const value = data as Record<string, unknown>
  return ['ready', 'unavailable', 'unsupported'].includes(String(value.status))
    && (value.selected === null || typeof value.selected === 'string')
    && Array.isArray(value.tracks) && value.tracks.every(track => track && typeof track.id === 'string'
      && typeof track.language === 'string' && ['manual', 'automatic'].includes(track.source))
    && Array.isArray(value.segments) && value.segments.every(segment => segment
      && Number.isFinite(segment.start) && segment.start >= 0
      && Number.isFinite(segment.end) && segment.end > segment.start && typeof segment.text === 'string')
}

export function SubtitlePanel({ url }: { url: string }) {
  const [transcript, setTranscript] = useState<Transcript | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function load(track?: string) {
    const abort = new AbortController()
    controller.current?.abort(); controller.current = abort
    setBusy(true); setError(''); setNotice(''); setTranscript(null)
    try {
      const response = await fetch('/api/subtitles', {
        method: 'POST', cache: 'no-store', signal: abort.signal,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, track_id: track }),
      })
      if (!response.ok) throw new Error('字幕取得失敗，請確認來源後重試。')
      const data: unknown = await response.json()
      if (!isTranscript(data)) throw new Error('字幕資訊不完整。')
      setTranscript(data)
    } catch (failure) {
      if (abort.signal.aborted) setNotice('字幕取得已取消。')
      else setError(failure instanceof Error ? failure.message : '字幕取得失敗。')
    } finally {
      if (controller.current === abort) { controller.current = null; setBusy(false) }
    }
  }

  async function download(format: 'srt' | 'vtt' | 'txt') {
    if (!transcript?.segments.length || busy) return
    const abort = new AbortController(); controller.current = abort
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await fetch('/api/subtitles/export', {
        method: 'POST', cache: 'no-store', signal: abort.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, segments: transcript.segments }),
      })
      if (!response.ok) throw new Error('字幕匯出失敗，請重新取得字幕。')
      const objectUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = objectUrl; link.download = `subtitles.${format}`; link.click()
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      setNotice(`${format.toUpperCase()} 已交給瀏覽器儲存。`)
    } catch (failure) {
      if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : '字幕匯出失敗。')
    } finally { controller.current = null; setBusy(false) }
  }

  return <section className="subtitle-panel" aria-label="影片字幕">
    <div className="panel-top"><h3>字幕與逐字稿</h3><span className="step">02 / 保留脈絡</span></div>
    <p>優先使用人工字幕；沒有人工字幕時選用自動字幕。</p>
    <div className="download-actions"><button type="button" className="primary" disabled={busy} onClick={() => void load()}>取得字幕</button>
      {busy && <button type="button" className="text-button" onClick={() => controller.current?.abort()}>取消取得</button>}</div>
    <div aria-live="polite">
      {busy && <p className="status">正在處理字幕…</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {notice && <p className="status">{notice}</p>}
      {transcript && transcript.tracks.length > 0 && <><label htmlFor="subtitle-track">字幕語言與來源</label>
        <select id="subtitle-track" value={transcript.selected ?? ''} disabled={busy} onChange={event => void load(event.target.value)}>
          {transcript.tracks.map(track => <option key={track.id} value={track.id}>{track.language} · {track.source === 'manual' ? '人工字幕' : '自動字幕'}</option>)}
        </select></>}
      {transcript?.status === 'unavailable' && <p className="status">這支影片目前沒有可取得的字幕。可以改試其他影片。</p>}
      {transcript?.status === 'unsupported' && <p className="status">來源有字幕，但目前不支援它的格式。</p>}
      {transcript?.status === 'ready' && <><p>{transcript.segments.length} 段字幕 · 時間與重複句均保留</p>
        <div className="download-actions">{(['srt', 'vtt', 'txt'] as const).map(format => <button type="button" className="text-button" key={format} disabled={busy} onClick={() => void download(format)}>匯出 {format.toUpperCase()} ↓</button>)}</div>
        <ol className="transcript">{transcript.segments.slice(0, 100).map((segment, index) => <li key={index}><time>{segment.start.toFixed(3)}–{segment.end.toFixed(3)} 秒</time><p>{segment.text}</p></li>)}</ol>
        {transcript.segments.length > 100 && <p>預覽前 100 段；匯出包含全部字幕。</p>}</>}
    </div>
  </section>
}
