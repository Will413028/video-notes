import assert from 'node:assert/strict'
import { createHash, randomUUID } from 'node:crypto'
import { setTimeout as delay } from 'node:timers/promises'

const base = 'http://127.0.0.1:3421'
const chunk = Buffer.alloc(65536)
for (let i = 0; i < chunk.length; i++) chunk[i] = i % 256
const expected = createHash('sha256')
for (let i = 0; i < 256; i++) expected.update(chunk)
const expectedHash = expected.digest('hex')

async function json(path) {
  const response = await fetch(base + path, { signal: AbortSignal.timeout(5000) })
  assert.equal(response.status, 200)
  return response.json()
}

async function transfer(kind, { cancel = false, mutation = '' } = {}) {
  const started = performance.now()
  const id = randomUUID()
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  let reader
  try {
    const response = await fetch(
      `${base}/api/fixture/${kind}?request_id=${id}&mutation=${mutation}`,
      { signal: controller.signal },
    )
    assert.equal(response.status, 200)
    reader = response.body.getReader()
    const first = await reader.read()
    assert.equal(first.done, false)
    const receivedAt = Date.now() / 1000
    const initial = await json(`/api/state/${id}`)
    assert.ok(receivedAt - initial.first_yield < 1, '第一 chunk 延遲超過 1 秒')
    assert.equal(initial.finished, false, 'upstream 完成前就應收到資料')
    if (cancel) {
      const abortedAt = Date.now() / 1000
      controller.abort()
      await reader.cancel().catch(() => {})
      const deadline = abortedAt * 1000 + 1000
      let closed
      do {
        closed = await json(`/api/state/${id}`)
        if (closed.closed) break
        await delay(25)
      } while (Date.now() < deadline)
      assert.equal(closed.closed, true, '取消後 upstream 未關閉')
      assert.ok(closed.closed_at - abortedAt <= 1, '取消後 upstream 關閉超過 1 秒')
      await delay(200)
      const later = await json(`/api/state/${id}`)
      assert.equal(later.produced, closed.produced, '取消後仍持續產生資料')
      assert.equal(later.finished, false)
      return { closed_after_ms: Math.round((closed.closed_at - abortedAt) * 1000), produced: closed.produced }
    }
    if (kind === 'sse') {
      const start = performance.now()
      assert.equal((await json('/api/health')).status, 'ok')
      assert.ok(performance.now() - start < 1000, '串流期間 health 過慢')
    }
    const buffers = [Buffer.from(first.value)]
    const decoder = new TextDecoder()
    let eventBuffer = ''
    let eventCount = 0
    let maxEventDelay = 0
    function inspectEvents(value) {
      if (kind !== 'sse') return
      eventBuffer += decoder.decode(value, { stream: true })
      let boundary
      while ((boundary = eventBuffer.indexOf('\n\n')) >= 0) {
        const event = eventBuffer.slice(0, boundary)
        eventBuffer = eventBuffer.slice(boundary + 2)
        assert.ok(event.startsWith('event: tick\ndata: '))
        const data = JSON.parse(event.slice('event: tick\ndata: '.length))
        assert.equal(data.index, eventCount++)
        const latency = Date.now() / 1000 - data.emitted_at
        maxEventDelay = Math.max(maxEventDelay, latency)
        assert.ok(latency < 1, 'SSE 事件延遲超過 1 秒')
      }
    }
    inspectEvents(first.value)
    while (true) {
      const result = await reader.read()
      if (result.done) break
      buffers.push(Buffer.from(result.value))
      inspectEvents(result.value)
    }
    const body = Buffer.concat(buffers)
    if (kind === 'file') {
      assert.equal(body.length, 16 * 1024 * 1024)
      assert.equal(createHash('sha256').update(body).digest('hex'), expectedHash)
    } else {
      assert.equal(eventCount, 30)
      assert.equal(eventBuffer, '')
    }
    return {
      first_chunk_ms: Math.round((receivedAt - initial.first_yield) * 1000),
      bytes: body.length,
      events: kind === 'sse' ? eventCount : undefined,
      max_event_delay_ms: kind === 'sse' ? Math.round(maxEventDelay * 1000) : undefined,
      duration_ms: Math.round(performance.now() - started),
    }
  } finally {
    clearTimeout(timeout)
    controller.abort()
    await reader?.cancel().catch(() => {})
  }
}

await json('/api/health')
for (const [name, operation] of [
  ['SSE 時序／內容與 health', () => transfer('sse')],
  ['16 MiB 檔案串流與 SHA256', () => transfer('file')],
  ['SSE 取消', () => transfer('sse', { cancel: true })],
  ['檔案取消', () => transfer('file', { cancel: true })],
  ['並行兩條 SSE', () => Promise.all([transfer('sse'), transfer('sse')])],
]) {
  const metrics = await operation()
  console.log(`PASS ${name} ${JSON.stringify(metrics)}`)
}
for (const [kind, options, message] of [
  ['sse', { mutation: 'buffer' }, /第一 chunk 延遲/],
  ['sse', { mutation: 'late_buffer' }, /SSE 事件延遲/],
  ['sse', { mutation: 'ignore_cancel', cancel: true }, /取消後仍持續產生資料/],
  ['file', { mutation: 'corrupt' }, /Expected values to be strictly equal/],
]) {
  await assert.rejects(() => transfer(kind, options), error =>
    error.name === 'AssertionError' && message.test(error.message))
  console.log(`PASS mutation ${options.mutation} 被驗收擋下`)
}
