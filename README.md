# video-notes

使用 Next.js + FastAPI 從零重做影片下載與 AI 摘要工具的學習專案。

功能參考：[liyupi/free-video-downloader](https://github.com/liyupi/free-video-downloader/tree/6783636e03e91b0beb82683d955beb475d7e66cc)。

目前提供範例解析／下載、YouTube／Bilibili 字幕 adapter、SRT／VTT／TXT 匯出，以及 PostgreSQL 帳號、註冊／登入／登出與 server-side session。平台驗收使用離線 fixtures；真實平台尚未 smoke。AI 與支付仍在後續階段；尚未部署。

## 本機執行

需要 Node 24+、pnpm 11.2.2、Python 3.12–3.14、uv、make，以及 PATH 中的 ffmpeg／ffprobe 與 PostgreSQL 16 工具（initdb、pg_ctl、createdb）。CI 使用 Node 24、Python 3.14；本機驗收使用 Node 26、Python 3.14。初次下載依賴依使用者授權進行。

在本 repo 根目錄安裝：

```sh
pnpm --dir frontend install --frozen-lockfile
uv sync --directory backend --frozen
```

分別開兩個 terminal，在根目錄執行：

```sh
make dev-api
make dev-web
```

`make dev-api` 會初始化專案獨占的 `backend/.runtime-db/` PostgreSQL、執行 Alembic migration，再啟動 API；Ctrl-C 時停止此 cluster，資料保留供下次啟動。只接受本機 Unix socket，根目錄權限 0700，不使用既有帳號／DB。資料由 PostgreSQL 16 建立，升級 PostgreSQL major version 前需另處理資料相容性。可以在「登入／註冊」使用你自己的 email 與 15–128 字元密碼，重新整理仍保持登入。

開啟 http://127.0.0.1:3422，點「帶入範例」，再點「解析影片」與「下載影片」。`fixture://learning-demo` 使用本機 ffmpeg 產生一秒 MP4，不會存取外部影片。也可以貼入 YouTube 或 Bilibili 單支影片 URL；此操作會存取該平台，成功與否取決於平台限制與固定版本適配。

## 驗收

在根目錄執行以下命令。E2E 自行啟動 production server，因此執行前須先停止自己的 dev-api/dev-web，避免占用 8422／3422。

```sh
make check
make test-integration
make test-e2e
make test-mutation
```

`make check` 包含 Python lint/format、TypeScript 與 production build。Browser 驗收需要 Playwright 所需的 Chromium 已存在；若需下載，先取得授權再執行 `pnpm --dir frontend exec playwright install chromium`。已有 Google Chrome 時，也可用 `PLAYWRIGHT_CHANNEL=chrome make test-e2e` 與 `PLAYWRIGHT_CHANNEL=chrome make test-mutation`。

`make test-integration CASE=download`／`make test-e2e CASE=download` 可選案例；CASE 沒有匹配時應失敗。mutation 在隔離 backend 副本破壞 title、URL policy、任務隔離、清理與格式選擇，要求對應測試失敗，不修改產品原始碼。

P3a 可用 `make test-integration CASE=auth`／`make test-e2e CASE=auth` 選測。驗收會建立臨時 PostgreSQL、執行 migration，結束停止並清除；不碰 dev 資料。auth mutation 另外破壞認證、CSRF、期限與密碼錯誤清理，要求具名斷言失敗。E2E 與 build 必須依序執行，避免讀到正在重建的 `.next`。

測試、build 與安裝輸出建議導入本 repo 的 ignored `.log`。沒有 `.env`／API key 也能跑此階段。

## 閱讀與修改

閱讀順序：frontend/app/video-form.tsx → frontend/lib/video.ts → backend/app/main.py → backend/app/downloads.py → backend/app/worker.py → backend/app/url_policy.py → backend/tests/test_worker.py。先讀 API 呼叫，再讀 worker 隔離與 process group 取消。

練習：修改 backend 範例的 title 或 duration，觀察畫面與測試的差異，再同步調整需求契約與測試預期值。這可驗證你理解資料是從 FastAPI 經同源 API 到 React state，而不是前端寫死。

P2 練習：調整範例短片的顏色／音頻；閱讀選定低畫質的回歸測試，確認 yt-dlp 不會改下載預設格式；追蹤 `AbortController` → backend disconnect → process group 終止 → UUID 目錄清理。暫存位於 ignored `backend/.runtime/`，可用 `VIDEO_NOTES_DOWNLOAD_DIR` 指定服務獨占目錄；不要指向其他程式的資料目錄。下載預設成品上限 128 MiB、兩個同時任務，前端會以 Blob 持有整支影片。

請從[階段計畫](docs/plans/2026-10-01-rebuild.md)閱讀範圍、待決事項與驗收方式。進度只記在該計畫。

P3 操作：解析範例後點「取得字幕」，切換 zh-Hant 人工／en 自動字幕，再匯出 SRT、VTT 或 TXT。逐字稿保留不同時間的重複句；頁面預覽最多100段，匯出包含全部。字幕只在記憶體處理，不保存全文。來源字幕上限2 MiB／10,000段，超過限制會報錯。可用 `make test-integration CASE=subtitles`／`make test-e2e CASE=subtitles` 選測；mutation 另交換 start/end，要求時間 mapping assertion 失敗。

P3 閱讀：`frontend/app/subtitle-panel.tsx` → `backend/app/main.py` → `app/downloads.py::VideoService.subtitles` → `app/worker.py` → `app/subtitles.py` → `tests/test_subtitles.py`。練習在範例加入一段不同時間的相同句子，核對畫面、SRT 時間與 TXT 行數；比較 json3 毫秒與 Bilibili 秒數如何轉成同一契約。設計與驗收見 [P3 設計](docs/plans/2026-10-01-rebuild/p3-design.md)／[P3 報告](docs/plans/2026-10-01-rebuild/p3-report.md)。

P3a 閱讀：`account-panel.tsx` → `lib/auth.ts` → `app/auth.py` → `app/database.py` → `migrations/versions/0001_auth.py` → `tests/test_auth.py`。練習調整 idle／absolute timeout，同步更新測試；追蹤瀏覽器 cookie 如何經 Next rewrite 送到 FastAPI，以及登出後舊 token 為何失效。token 只存 HttpOnly cookie，前端不使用 localStorage；資料庫只存 token digest。
