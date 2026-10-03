import { test, expect } from '@playwright/test'
import { readdir } from 'node:fs/promises'
import { resolve } from 'node:path'

test('download：取消後可以再次操作且任務檔清理', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '帶入範例' }).click()
  await page.getByRole('button', { name: '解析影片' }).click()
  await page.getByRole('button', { name: '下載影片' }).click()
  await page.getByRole('button', { name: '取消下載' }).click()
  await expect(page.getByText('下載已取消。')).toBeVisible()
  await expect(page.getByRole('button', { name: '下載影片' })).toBeEnabled()
  await expect.poll(async () => (await readdir(resolve('../backend/.runtime'))).filter(name => name.startsWith('job-'))).toEqual([])
})

test('download：範例格式可下載 MP4', async ({ page }) => {
  test.setTimeout(180000)
  await page.goto('/')
  await page.getByRole('button', { name: '帶入範例' }).click()
  const parsed = page.waitForResponse(response => response.url().endsWith('/api/parse'))
  await page.getByRole('button', { name: '解析影片' }).click()
  expect((await parsed).status()).toBe(200)
  await expect(page.getByLabel('下載格式')).toHaveValue('demo-360')
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: '下載影片' }).click()
  const download = await pending
  expect(download.suggestedFilename()).toBe('用 AI 建立你的學習工作流.mp4')
  expect(await download.failure()).toBeNull()
  await expect(page.getByText('影片已交給瀏覽器儲存。')).toBeVisible()
})

test('parse：真實前後端薄路徑顯示影片標題', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByRole('button', { name: '帶入範例' }).click()
  const response = page.waitForResponse(result => result.url().endsWith('/api/parse'))
  await page.getByRole('button', { name: '解析影片' }).click()
  const parsed = await response
  expect(parsed.status()).toBe(200)
  if (process.env.VIDEO_NOTES_TITLE_MUTATION === '1') {
    expect((await parsed.json()).title).toBe('title-removed')
  }
  await expect(page.getByRole('heading', { name: '用 AI 建立你的學習工作流' }), 'TITLE_MAPPING_ASSERTION').toBeVisible()
  await expect(page.getByText('12 分 34 秒')).toBeVisible()
  await expect(page.getByText('影片資訊已準備好')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('desktop.png'), fullPage: true })
})

test('parse：未知來源顯示錯誤，之後可以重試範例', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('影片連結').fill('https://example.com/not-available')
  await page.getByRole('button', { name: '解析影片' }).click()
  await expect(page.getByRole('region', { name: '影片解析' }).getByRole('alert')).toContainText('目前支援 YouTube 與 Bilibili')
  await page.getByRole('button', { name: '帶入範例' }).click()
  await page.getByRole('button', { name: '解析影片' }).click()
  await expect(page.getByRole('heading', { name: '用 AI 建立你的學習工作流' })).toBeVisible()
})

test('parse：手機版可操作且沒有水平溢出', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: '帶入範例' }).click()
  await page.getByRole('button', { name: '解析影片' }).click()
  await expect(page.getByRole('heading', { name: '用 AI 建立你的學習工作流' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true })
})
