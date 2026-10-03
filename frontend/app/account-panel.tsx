'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { authenticate, currentUser, logout, type User } from '../lib/auth'

export function AccountPanel() {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(true)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    currentUser(controller.signal).then(setUser).catch(failure => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : '請重試。')
    }).finally(() => { if (!controller.signal.aborted) setChecking(false) })
    return () => controller.abort()
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || checking) return
    setBusy(true); setError('')
    try {
      setUser(await authenticate(mode, email, password))
      setPassword(''); setOpen(false)
    } catch (failure) { setError(failure instanceof Error ? failure.message : '請重試。') }
    finally { setBusy(false) }
  }

  async function signOut() {
    if (busy) return
    setBusy(true); setError('')
    try { await logout(); setUser(null); setPassword('') }
    catch (failure) { setError(failure instanceof Error ? failure.message : '請重試。') }
    finally { setBusy(false) }
  }

  return <section className="account" aria-label="帳號">
    <div className="account-row">
      {checking ? <span role="status">確認登入狀態…</span> : user ? <><span>已登入：{user.email}</span><button className="text-button" disabled={busy} onClick={() => void signOut()}>登出</button></> : <button className="text-button" onClick={() => { setOpen(!open); setError('') }}>登入／註冊 →</button>}
    </div>
    {open && !user && <form onSubmit={submit} className="account-form">
      <h2>{mode === 'login' ? '歡迎回來' : '建立你的帳號'}</h2>
      <label htmlFor="account-email">Email</label><input id="account-email" type="email" autoComplete="email" required maxLength={254} value={email} disabled={busy} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="account-password">密碼</label><input id="account-password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={15} maxLength={128} value={password} disabled={busy} onChange={event => setPassword(event.target.value)} />
      <p className="account-help">使用 15–128 字元的密碼。</p>
      <div className="download-actions"><button className="primary" disabled={busy || checking}>{busy ? '處理中…' : mode === 'login' ? '登入' : '註冊'}</button><button type="button" className="text-button" disabled={busy} onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); setPassword('') }}>{mode === 'login' ? '還沒有帳號？註冊' : '已有帳號？登入'}</button></div>
    </form>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>
}
