import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'video-notes · 把影片變成你的知識',
  description: '整理影片內容，留下值得回看的知識。',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-Hant"><body>{children}</body></html>
}
