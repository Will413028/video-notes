# 需求與參考盤點

核對日期：2026-10-01。原專案快照：`6783636e03e91b0beb82683d955beb475d7e66cc`。

來源 U1：Will 指定完整重做、Next.js + FastAPI、personal/video-notes、全部功能含登入額度 Stripe。
來源 R1：[原專案 README](https://github.com/liyupi/free-video-downloader/blob/6783636e03e91b0beb82683d955beb475d7e66cc/README.md)。
來源 R2：[原專案 backend](https://github.com/liyupi/free-video-downloader/tree/6783636e03e91b0beb82683d955beb475d7e66cc/backend)。
來源 R3：[原專案 frontend](https://github.com/liyupi/free-video-downloader/tree/6783636e03e91b0beb82683d955beb475d7e66cc/frontend)。

原實作證明功能如何串接；本次未啟動原服務，不視為所有平台與宣傳規模的實測證據。這是獨立新系統，不搬移原服務的資料或部署。

| ID | 類別與需求 | 來源 | 去向與步驟 |
|---|---|---|---|
| R01 | 畫面：輸入 URL、影片資訊、格式與解析錯誤 | U1/R1/R3 | 重寫，P2 |
| R02 | API/流程：yt-dlp 解析、多清晰度、服務端下載與直鏈 | R1/R2 | 保留能力並隔離適配，P2 |
| R03 | API：抖音專用解析 | R1/R2 | 重寫，P7；可用性由 spike 驗證 |
| R04 | 實體/API：帶 start/end/text 的字幕、人工與自動字幕選擇 | R2 | 標準化，P3 |
| R05 | 畫面/流程：SSE 摘要、進度、失敗與完成 | R1/R2/R3 | 重寫，P4 |
| R06 | 畫面：Markdown 心智圖、互動、全螢幕、PNG/SVG 匯出 | R1/R3 | 重寫，P5 |
| R07 | 流程：基於影片字幕的 AI 問答 | R1/R2 | 重寫，P5 |
| R08 | API：SRT/VTT/TXT 字幕匯出 | R1/R3 | 重寫，P3 |
| R09 | 實體/畫面：users、註冊登入、會員狀態 | U1/R1/R2 | 重寫，P3a |
| R10 | 實體/流程：每日免費額度、VIP 權限 | U1/R1/R2 | 重寫，P4；額度規則 D3 |
| R11 | 實體/流程：orders、Checkout、Webhook、會員期限 | U1/R2 | 重寫，P6；單次或續訂 D4 |
| R12 | 畫面：功能、操作說明、方案、SEO/GEO | R1/R3 | 重寫品牌與文案，P7；不承諾排名 |
| R13 | 流程：本機執行、CI、部署 | R1；部署屬推論 | P1/P8；實際託管 D5 |
| R14 | 長字幕完整處理與時間戳引用 | 推論（前一輪建議，尚未拍板） | D2 決定，P4/P5 |

## 已知缺陷處置

| ID | 靜態證據 | 建議處置 | 失敗測試／決定 |
|---|---|---|---|
| B1 | api_summarize.py 的 chat_with_video 不檢查 optional user | 修：所有 AI 入口共用認證及成本政策 | 匿名 chat 不得呼叫模型；D3 |
| B2 | summarizer.py 截取前 15000/12000 字元 | D2 決定；不默默宣稱涵蓋全片 | 答案位於末段的 fixture |
| B3 | async API 直接迭代同步模型串流 | 修：async SDK 或隔離阻塞 I/O | 慢串流期間 health 與第二串流仍回應 |
| B4 | 摘要在取字幕前扣額度 | D3 決定預留、結算、失敗釋放語意 | 無字幕、取消、重試、併發額度案例 |
| B5 | complete_order 先讀 pending 再更新；更新未帶 pending 條件 | 修：原子狀態轉換；單次重送與併發重送都驗證 | 同一事件雙送只增加一次會員期限 |
| B6 | thumbnail proxy 接受任意 URL 並跟隨 redirect | 修：限制 scheme、host、解析 IP 與重導向 | loopback/private IP/redirect fixture 均拒絕 |

## 非功能需求

- 測試不得依賴真實平台、模型或支付；真實 smoke 獨立 opt-in。
- 串流驗收以人工延遲 fixture：第一事件在 fixture 首次 yield 後 1 秒內呈現；並行 2 條串流期間 health 回應 1 秒內。正式效能門檻待 D5。
- 同一支付事件與同一額度 request id 併發重送不得重複產生權益／扣次。
- 未登入 AI 請求不得消耗模型費用；日誌不包含字幕全文、密碼或金鑰。
- 本機下載暫存檔採 P2 的完成／取消／失敗立即清理與重啟孤兒清理預設；保存供重下載須另決定。字幕／問答保存期限、影片長度與費用上限：D2/D3/D5 未決。
- SEO 驗收 metadata、canonical、robots、sitemap、伺服器輸出的可讀頁面內容，不以排名為驗收。

## 外部介面

| 介面 | 用途／限制 | 官方來源與重查方法 |
|---|---|---|
| Next.js rewrites | 同源轉送候選；SSE 與大檔必須實測 | https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites |
| FastAPI async | 阻塞工作須隔離，不直接放入 event loop | https://fastapi.tiangolo.com/async/ |
| yt-dlp / ffmpeg | 解析、下載、合併；平台支持持續變動 | https://github.com/yt-dlp/yt-dlp ；實作前查 supported sites 與 pinned 版本 |
| DeepSeek | 原作模型供應商；新作選擇與額度待決 | https://api-docs.deepseek.com/ ；P0 重查價格與限制，本次頁面讀取失敗 |
| Stripe Checkout | 單次或訂閱；Webhook 驗簽與可靠履約 | https://docs.stripe.com/checkout/fulfillment ；P6 重查事件與 test mode |

查詢日期：2026-10-01。官方文件查核不等於執行測試。採用版本與成本在實作前再次核對。

## 學習與產品風險

目前只有 Will 的學習需求證據，沒有付費需求證據。可先完成學習版本；是否上線商用與做用戶驗證列 D5，不因加入 Stripe 就假設要真實收款。

盤點來源取得方式：GitHub recursive tree API `GET /repos/liyupi/free-video-downloader/git/trees/master?recursive=1`，並讀取快照的 README、backend/main.py、api_summarize.py、summarizer.py、downloader.py、api_payment.py、database.py、frontend/src/api/summarize.js 與 VideoSummary.vue 的相關區段。表格是功能清單，不宣稱精確 endpoint 總數。
