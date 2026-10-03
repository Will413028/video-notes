# P3 沿用盤點

| 機制 | 原因與今天的約束 | 從零設計的做法／來源 | 本次決定與重新評估條件 |
|---|---|---|---|
| yt-dlp worker／urllib socket guard | P2 已處理 provider extraction／SSRF，字幕也屬匿名影片來源 I/O | [yt-dlp subtitle metadata](https://github.com/yt-dlp/yt-dlp#subtitle-options) 提供人工／automatic tracks，獨立 worker 可取消 | 保留單一入口與 transport；需要登入字幕時先決定 cookie 邊界，不新增旁路 |
| 同一 semaphore、45秒 timeout | 本機學習服務，影片與字幕共享 CPU／網路上限 | Python asyncio bounded concurrency；不需要持久 queue | 沿用兩 slots，新增有界 stdout reader；公開流量／背景 job 需求由 P8 重新評估 |
| 平台 JSON + 通用 timed text parsers | 原作依賴既有字幕，無 ASR 需求；固定 yt-dlp Bilibili emits inline SRT | [WebVTT](https://www.w3.org/TR/webvtt1/) cue timestamps，平台結構化 JSON 與 SRT adapter | 支援 json3／Bili JSON／VTT／SRT，輸出統一 segments；其他格式明示 unsupported，新增格式需獨立 fixtures |
| 語言／來源選擇 | 人工優先是 P3 要求，尚無帳號語言偏好 | metadata 分 manual／automatic，再讓使用者明示選軌 | 預設人工優先＋字典序，來源 ai-* 視為 automatic；語言偏好需求出現才加入帳號設定 |
| request／response in memory | D2 全文保存未決且不擋 P3；下載 session 不需要全文資料庫 | 本階段 stateless extract→normalized segments→export；body／response／段數有上限 | 不保存字幕，不寫 logs；D2 若選全文持久化，另定 retention／privacy／ownership |
| 匯出 endpoint 接收已取得 segments | 同一語言反覆取得來源增加延遲且可能內容不同 | 驗證 segments 後 deterministic serializer | 匯出使用當前畫面內容，無外部 I/O；SRT／VTT純文字、TXT不帶時間；樣式需求出現再擴充 |
| 毫秒精度與文字標準化 | 跨平台時間格式不同；SRT／VTT需固定時間語法 | 時間 round-half-up 到毫秒，保留時間序與重複cue，decode markup為純文字 | 不去重、不融合 cue；異常時間拒絕；樣式／roll-up captions專門需求出現才另定轉換規則 |
| request body／worker result 驗證 | JSON body 與 provider 輸出是不同的信任邊界 | ASGI receive 計數在 JSON 解碼前，worker回應再經 Pydantic | 大小／型別各守自己的邊界；增加新字幕endpoint時使用同一限制 |
| no-store response middleware | auth及字幕均不快取；原 BaseHTTP middleware只改headers，卻包裝receive | [Starlette pure ASGI middleware](https://www.starlette.io/middleware/) 可只攔 send response.start | 改純ASGI，保留原receive與串流；新增需要body處理的middleware前先驗取消／cleanup，不恢復 BaseHTTP wrapper |
| stdout cap／程序清理 | 大字幕不能使用無界communicate；超限後 pipe 可能仍有資料 | [Python subprocess pipes](https://docs.python.org/3/library/asyncio-subprocess.html) 要同時讀取輸出與等候程序，避免pipe阻塞 | 有界 reader超限即拒絕，清理時discard剩餘stdout，不保留bytes；改transport或subprocess時保留超量輸出／取消測試 |
| 錯誤分類／外部內容抑制 | provider URL可能簽名且不適合顯示給使用者 | provider成功無字幕和HTTP處理失敗分開；worker邊界通用錯誤 | unavailable／unsupported／422／413／502有契約；不輸出provider traceback或全文logs |
| monitor終止訊號 | `Request.is_disconnected`使用cancel scope，原task.cancel可能被poll吞掉；監控是週期回傳的request-local工作 | [asyncio.Event](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event)明示協作結束 | finally先set Event，monitor本次poll完成後不再讀request；communication仍用native cancellation，兩者責任不同；修改polling或middleware需保留吞取消回歸 |

本專案沒有原作完整 source checkout，需求對照來自既有 requirements 附件；不把原作程式碼當作本次實作。真平台字幕 smoke 未執行，與 fixture adapter correctness 分開驗收。
