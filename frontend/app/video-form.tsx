'use client'

import { useRef, useState, type FormEvent } from 'react'
import { DEMO_URL, parseVideo, type VideoInfo } from '../lib/video'
import { SubtitlePanel } from './subtitle-panel'

export function VideoForm() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<VideoInfo | null>(null)
  const [error, setError] = useState('')
  const [parsedUrl, setParsedUrl] = useState('')
  const [format, setFormat] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadStatus, setDownloadStatus] = useState('')
  const controller = useRef<AbortController | null>(null)

  async function download(direct = false) {
    if (!result || downloading) return
    const abort = new AbortController()
    controller.current = abort
    setDownloading(true); setError(''); setDownloadStatus('正在準備影片…')
    try {
      const response = await fetch(direct ? '/api/direct' : '/api/download', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: abort.signal,
        body: JSON.stringify({ url: parsedUrl, format_id: format }),
      })
      if (!response.ok) throw new Error('下載失敗，請重新解析或選擇格式。')
      if (direct) {
        const data: unknown = await response.json()
        if (typeof data !== 'object' || data === null || !('url' in data) || typeof data.url !== 'string') throw new Error('直鏈資訊不完整。')
        const target = new URL(data.url)
        if (!['http:', 'https:'].includes(target.protocol)) throw new Error('直鏈格式不正確。')
        await navigator.clipboard.writeText(target.href)
        setDownloadStatus('已複製直鏈；連結可能過期。')
      } else {
        if (!response.body) throw new Error('下載內容不完整。')
        const reader = response.body.getReader()
        const chunks: ArrayBuffer[] = []
        const total = Number(response.headers.get('Content-Length'))
        let received = 0
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          received += value.byteLength
          chunks.push(value.slice().buffer)
          setDownloadStatus(total ? `正在接收影片 ${Math.floor(received / total * 100)}%` : `已接收 ${Math.round(received / 1024)} KB`)
        }
        const objectUrl = URL.createObjectURL(new Blob(chunks))
        const link = document.createElement('a')
        link.href = objectUrl
        link.download = `${result.title.replace(/[\\/:*?"<>|]/g, '_')}.${result.formats.find(item => item.format_id === format)?.ext ?? 'mp4'}`
        link.click()
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
        setDownloadStatus('影片已交給瀏覽器儲存。')
      }
    } catch (failure) {
      if (abort.signal.aborted) setDownloadStatus('下載已取消。')
      else { setError(failure instanceof Error ? failure.message : '下載失敗。'); setDownloadStatus('') }
    } finally { controller.current = null; setDownloading(false) }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    setLoading(true)
    setError('')
    setResult(null)
    setDownloadStatus('')
    try {
      const video = await parseVideo(url.trim())
      setResult(video); setParsedUrl(url.trim()); setFormat(video.formats[0]?.format_id ?? '')
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : '解析失敗，請重試。') }
    finally { setLoading(false) }
  }

  return (
    <section className="workspace" aria-label="影片解析">
      <div className="panel-top"><span className="step">01 / 開始整理</span><span className="demo-badge">範例體驗</span></div>
      <form onSubmit={submit}>
        <label htmlFor="video-url">影片連結</label>
        <div className="input-row">
          <input id="video-url" required maxLength={2048} value={url} disabled={loading || downloading}
            onChange={event => setUrl(event.target.value)} placeholder="貼上想學習的影片連結" />
          <button className="primary" type="submit" disabled={loading || downloading}>{loading ? '解析中…' : '解析影片 ↗'}</button>
        </div>
        <div className="input-help"><p>YouTube、Bilibili，或先試試範例影片。</p><button type="button" className="text-button" disabled={loading || downloading} onClick={() => { setUrl(DEMO_URL); setError(''); setResult(null); setDownloadStatus('') }}>帶入範例 →</button></div>
      </form>
      <div aria-live="polite" aria-atomic="true">
        {loading && <p className="status">正在讀取影片資訊…</p>}
        {error && <p role="alert" className="error">{error}</p>}
        {result && <article className="result">
          <div className="video-art" aria-hidden="true"><span>▶</span><small>LEARNING SESSION</small></div>
          <div className="video-detail"><p className="eyebrow">已解析 · {result.source === 'demo' ? '範例影片' : result.source}</p><h2>{result.title}</h2><p>{result.uploader} <span className="separator">/</span> {Math.floor(result.duration_seconds / 60)} 分 {result.duration_seconds % 60} 秒</p><span className="ready">影片資訊已準備好</span></div>
        </article>}
        {result && <div className="download-panel">
          {result.formats.length ? <><label htmlFor="video-format">下載格式</label><select id="video-format" value={format} disabled={downloading} onChange={event => setFormat(event.target.value)}>{result.formats.map(item => <option key={item.format_id} value={item.format_id}>{item.label}</option>)}</select><div className="download-actions"><button className="primary" type="button" disabled={downloading} onClick={() => void download()}>下載影片 ↓</button>{result.source !== 'demo' && !result.formats.find(item => item.format_id === format)?.requires_merge && <button className="text-button" type="button" disabled={downloading} onClick={() => void download(true)}>複製下載直鏈</button>}{downloading && <button type="button" className="text-button" onClick={() => controller.current?.abort()}>取消下載</button>}</div></> : <p>這支影片目前沒有可下載的格式。</p>}
          {downloadStatus && <p className="status">{downloadStatus}</p>}
        </div>}
      </div>
      {result && <SubtitlePanel key={parsedUrl} url={parsedUrl} />}
      {!result && !loading && !error && <div className="empty"><span className="empty-icon" aria-hidden="true">↗</span><p>下一段值得記住的內容，從這裡開始。</p></div>}
    </section>
  )
}
