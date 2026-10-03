import { VideoForm } from './video-form'
import { AccountPanel } from './account-panel'

export default function Home() {
  return (
    <main className="shell">
      <header><a href="/" className="brand">video<span>notes</span><span className="brand-dot">●</span></a><span className="edition">你的影片學習空間</span></header>
      <section className="intro">
        <p className="eyebrow">WATCH LESS. LEARN MORE.</p>
        <h1>看過的影片，<br />留下來的<span>知識。</span></h1>
        <p className="lead">從一個連結開始，把值得學的內容整理成能回看的筆記。</p>
      </section>
      <VideoForm />
      <AccountPanel />
      <footer><span>為好奇心留一個位置。</span><span>video-notes / 01</span></footer>
    </main>
  )
}
