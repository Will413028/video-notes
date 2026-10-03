# P0：routing spike

這是隔離的實驗程式，已安裝依賴並通過 production routing 驗收，詳見[報告](report.md)。僅監聽 loopback，不使用影片、模型、支付或任何憑證。

閱讀順序：`next.config.mjs` 的 rewrite → `upstream.py` 的 async generator → `verify.mjs` 的逐 chunk 接收、取消與 hash 驗證。

需要重新下載依賴時先取得授權，在本目錄依 lockfile 安裝：

```sh
pnpm install --frozen-lockfile
uv sync --frozen --no-python-downloads
```

分別啟動兩個程序，在本目錄執行：

```sh
uv run --no-sync uvicorn upstream:app --host 127.0.0.1 --port 8421
pnpm build
pnpm start
```

Next.js production server 與 upstream 就緒後，於本目錄執行 `pnpm verify`。build、start、uvicorn、verify 已跑通；表列 frozen 安裝是依既有 lockfile 重現方式，本輪安裝時尚未有 lockfile。輸出可導到本目錄的 ignored .log 檔。驗收後停止自己啟動的兩個程序。

mutation 驗收涵蓋全部緩衝、第一事件後緩衝、取消後工作持續產生資料、檔案內容損壞。取消 mutation 注入一秒的孤兒工作；正式模型與 downloader 仍需各自驗證取消，不能單憑 routing spike 證明任意 SDK 都能停止底層工作。

修改練習：把 SSE delay 改成 0.2 秒，預測第一事件與完整回應時間的差異，再重新執行 verifier。
