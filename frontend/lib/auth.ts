export type User = { id: string; email: string }

function readUser(data: unknown): User {
  if (typeof data !== 'object' || data === null || !('id' in data) || !('email' in data)
    || typeof data.id !== 'string' || typeof data.email !== 'string') throw new Error('帳號資料不完整。')
  return { id: data.id, email: data.email }
}

export async function currentUser(signal?: AbortSignal): Promise<User | null> {
  const response = await fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store', signal })
  if (response.status === 401 || response.status === 503) return null
  if (!response.ok) throw new Error('暫時無法確認登入狀態。')
  return readUser(await response.json())
}

export async function authenticate(action: 'login' | 'register', email: string, password: string): Promise<User> {
  const response = await fetch(`/api/auth/${action}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'video-notes' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) {
    if (response.status === 409) throw new Error('此 email 已註冊，請切換登入。')
    if (response.status === 401) throw new Error('Email 或密碼不正確。')
    if (response.status === 422) throw new Error('請確認 email 與密碼長度（15–128 字元）。')
    if (response.status === 429) throw new Error('嘗試次數過多，請稍後再試。')
    if (response.status === 503) throw new Error('本機資料庫尚未啟動。')
    throw new Error('暫時無法登入，請稍後再試。')
  }
  return readUser(await response.json())
}

export async function logout(): Promise<void> {
  const response = await fetch('/api/auth/logout', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'video-notes' },
    body: '{}',
  })
  if (!response.ok) throw new Error('登出失敗，請重試。')
}
