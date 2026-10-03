# video-notes

以 Next.js 與 FastAPI 從零實作影片下載與 AI 學習工具。

- 前端使用 Next.js；後端使用 FastAPI。
- 功能範圍包含影片解析下載、字幕匯出、AI 摘要、心智圖、問答、登入、額度與 Stripe。
- 需求與階段計畫見 `docs/plans/2026-10-01-rebuild.md`；未決項須先拍板才實作。
- 原專案是功能參考，不直接複製程式碼或品牌素材。
- 產品程式在 `frontend/` 與 `backend/`；解析、下載與字幕取得使用隔離 yt-dlp worker，字幕匯出使用已驗證的 segments，不去重不同時間的相同句子；驗收以離線 fixtures 進行。API 契約見 `docs/plans/2026-10-01-rebuild/api-contract.md`，認證／資料庫決定見同目錄 `architecture-decision.md`。
- 決策紀錄（ADR）：`docs/adr/`。
- 登入使用 FastAPI server-side session、HttpOnly cookie 與 PostgreSQL；auth POST 使用 exact Origin／自訂 header／JSON CSRF 防護，validation error 不回傳 input／ctx。認證資料只由後端判定，前端不儲存 token。
- 在 repo 根目錄，`make check`、`make test-integration`、`make test-e2e`、`make test-mutation` 是共用驗收入口；下載測試需要 PATH 中的 ffmpeg／ffprobe。CI 使用相同入口。
- E2E／mutation 需要 Chromium，並自行啟動 3422／8422 的服務；先停止自己的 dev service，不重用或殺掉未知程序。安裝、啟動與閱讀順序見 README。
- DB 驗收用 scripts/with-test-postgres.py 建立獨占臨時 cluster；不得直接對 dev／外部 DB 跑 downgrade 或清除測試。先完成 build，再跑 browser／mutation；不可邊重建 .next 邊驗收。
- Routing 實驗位於 `docs/plans/2026-10-01-rebuild/spike/`。
- 在 spike 目錄，`pnpm build`、`pnpm start`、`uv run --no-sync uvicorn upstream:app --host 127.0.0.1 --port 8421` 與 `pnpm verify` 已驗證可執行。verify 需要先啟動兩個本機 service；結果見該目錄的 `report.md`。
