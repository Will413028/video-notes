# P0a 驗收報告

日期：2026-10-01。環境：macOS arm64、Node 26.10.0、pnpm 11.2.2、Python 3.14.7、uv 0.12.19。套件實際解析為 Next.js 16.3.7、React/React DOM 19.3.0、FastAPI 0.142.2、Starlette 1.7.0、uvicorn 0.54.0；版本固定於 pnpm-lock.yaml／uv.lock。

## 結論與適用範圍

本機 Next.js production rewrite 在 `compress:false` 下通過逐事件串流、取消與檔案轉送驗收。這是 D1 同源 routing 選項的可行性證據，尚未替 Will 決定認證與資料庫。不代表託管平台／CDN／反向代理也已驗證。

原始 gzip 設定的反例：同一 fixture，直連 FastAPI 首批資料約 53 ms；經 Next.js 約 3045 ms 才收到全部 650 bytes，content-encoding 為 gzip。修正後使用下表正式驗收。P1 若採同源轉送，須保留串流延遲 gate，不能只檢查最終 body。

## 重跑入口

工作目錄為本 report 所在的 spike 目錄。已跑命令：`pnpm install`、`uv sync --python /opt/homebrew/bin/python3`、`pnpm build`、`uv run --no-sync uvicorn upstream:app --host 127.0.0.1 --port 8421`、`pnpm start`、`pnpm verify`。兩個 service 僅綁定 loopback；驗收後停止。

`pnpm verify` exit 0。production build exit 0。

| 驗收 | 最後一輪實測 | 結果 |
|---|---|---|
| SSE 30 事件／內容／health | 首 chunk 1 ms；最大事件延遲 17 ms；總時長 3088 ms；串流期間 health <1 秒 | 通過 |
| 16 MiB 檔案 | 16,777,216 bytes；首 chunk 2 ms；總時長 2932 ms；SHA256 與 deterministic fixture 相同 | 通過 |
| SSE 取消 | abort 後 18 ms upstream 關閉，produced 停留 1 | 通過 |
| 檔案取消 | abort 後 1 ms upstream 關閉，produced 停留 1 | 通過 |
| 兩條並行 SSE | 各 30 事件；首 chunk 3／1 ms；最大事件延遲 9／7 ms；各 3055 ms；health <1 秒 | 通過 |
| buffer mutation | 首 chunk 延遲斷言攔下 | 通過 |
| late_buffer mutation | 第一事件即送，後續事件緩衝；逐事件延遲斷言攔下 | 通過 |
| ignore_cancel mutation | transport 已關閉但孤兒工作增加 produced；停止斷言攔下 | 通過 |
| corrupt mutation | 檔案長度相同、bytes 被改動；SHA256 斷言攔下 | 通過 |

## 獨立 source review

第一次發現 3 項：只測第一 chunk、取消 mutation 只改旗標、取消 deadline 可能被 polling 延遲繞過。修正如下，第二輪全部復核通過：

- F1：每個事件附 emitted_at，讀取中解析與測量；late_buffer 提供反例。
- F2：ignore_cancel 實際啟動持續一秒的孤兒工作，檢查 produced 不得增加。
- F3：abort 前記錄時間，與 upstream closed_at 對帳，嚴格檢查 1 秒門檻。

主 agent 在審查修正後重跑 build 與完整驗收；表格取最後一輪輸出。

## 未跑

- 真實影片／平台字幕、模型與成本、Stripe、正式託管：分別屬 P0b、後續產品階段與 D5；本次未使用憑證或外部服務呼叫。
- 正式 downloader／模型 SDK 的取消：此 spike 只證明 local routing 與 fixture generator；各 adapter 落地後獨立驗證。

## 下一步閱讀與修改

先讀 next.config.mjs → upstream.py → verify.mjs。修改練習：把 SSE interval 改為 0.2 秒，重啟 upstream 並跑 verify；第一事件仍應很快，完整串流時間約加倍。此練習不影響尚未開始的產品程式碼。
