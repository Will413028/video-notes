# P2：解析與下載驗收

日期：2026-10-01。本機 macOS arm64、Python 3.14.7、Node 26.10.0、既有 ffmpeg 9.0.2，yt-dlp 固定 2026.8.19；此次依賴下載經 Will 授權。沒有下載真實影片、讀 cookies、登入外部平台或呼叫模型／Stripe。

## 交付與閱讀

- `/api/parse` 增加原生 muxed／可本機合併格式；入口 YouTube／Bilibili／b23.tv exact hosts，保留 deterministic 範例。
- `/api/download` 串流檔案，`/api/direct` 提供 muxed 直鏈；server 重新解析並驗證 format，使用者不能指定任意下載 selector 或媒體 URL。
- 前端格式選擇、下載／取消／傳輸進度、錯誤重試與直鏈複製。
- 每任務獨立 worker／process group／UUID 目錄；worker timeout、傳輸 timeout、同時任務限制、成品／暫存大小預算；正常、錯誤、取消、重啟清理。
- 固定 urllib transport 與 worker socket public-IP guard；不使用 external downloader／manifest 格式、不讀 cookies／config／proxy／plugins、不下載 JS runtime。ffmpeg 只處理本機檔。

先讀 [README](../../../README.md)，接著 `main.py` → `downloads.py` → `worker.py` → `url_policy.py`；格式／合併測試在 `test_worker.py`，取消與清理在 `test_downloads.py`。API 見 [契約](api-contract.md)，取捨見 [設計](p2-design.md)。

## 驗收證據

| 入口 | 結果 |
|---|---|
| `make check` | Python lint／format、TypeScript、Next production build 通過 |
| `make test-integration` | 38 passed：入口繞過、private IP、混合 DNS／重綁、實際 socket 目的地、任務隔離、重啟／失敗／傳輸中斷清理、worker timeout、child process 終止、暫存預算、MP4 音訊／影像、真正 yt-dlp 原生下載與 ffmpeg 合併、直鏈、選定格式與 stale merge 狀態 |
| `make test-e2e` | 5 passed：同源範例解析、未知來源重試、下載儲存、取消與任務清理、390px 手機操作 |
| `make test-mutation` | 通過：title 與 5 項 download mutations，隔離副本破壞行為後由指定失敗攔下 |
| 自有檔案 diff／Markdown 連結與 vault gates | 通過；parent 的既有 concurrent 變更未修改 |
| 視覺 QA | 實際檢視 desktop／mobile PNG；格式選擇與下載控制無裁切 |

測試使用本機產生的音影片，provider fixture 替換 `extract_info` 的來源與 network response，保留真實 `process_video_result(download=False)`、原生下載器與 merger；不等同真平台可用性證明。輸出留在 ignored `check-p2.log`、`backend/tests-p2.log`、`e2e-p2.log`。

## 獨立審查與累積 findings

- 設計審查 1 項，記 1、改／提／駁回 0：Blob 在瀏覽器持有完整影片的記憶體取捨，已記錄目前上限與提高容量／公開服務的重新評估條件。審查使用原作靜態盤點，沒有直接逐行核對原作快照。
- F1 已修：yt-dlp 初始化 selector 與預處理的 `requested_formats` 都會保留預設選擇；設定實際 selector、縮限 formats、清除舊 merge fields。`test_muxed_selection_discards_preprocessed_merge_tracks` 修正前確實失敗（`backend/regression-before-p2.log`），修正後通過。
- F2 已修：合併前後來源／成品共存，舊 hook 重複計算且沒有持續監控。分開 raw／final 上限與 workspace 預算，parent 每 50ms 監控並終止 group，對應 budget 測試通過。輪詢期間可能短暫超量，已記錄在設計。
- 複核結論：F1／F2 已修，未見重要殘留；主 agent 自行重跑驗收。`noprogress=True` 避免 worker stdout 混入 yt-dlp 進度，測試要求 stdout 保持空白直到 JSON 結果。
- 指令檔對帳更新產品能力與驗收規則兩處；歷史結果留本報告，沒有寫入指令檔。

## 未驗證與下一步

- 真實 YouTube／Bilibili smoke 未跑：本次僅授權依賴下載。沒有 cookies／JS runtime，部分影片可能沒有可用格式或受到平台限制；本報告不宣稱真平台已驗收。
- GitHub CI／Linux + Node24 未跑：尚無 remote；CI 使用同一 make 入口並要求 ffmpeg／ffprobe。
- Starlette TestClient 使用 httpx 的 deprecation warning 保留，38 tests 已通過，尚未遷移 httpx2。
- 尚未 commit／stage／push；repo main 沒有 commit／remote，保留可供 Will 閱讀修改的工作區。
- 下一階段依主計畫為 P3a 登入與持久化：依 D1 server session、HttpOnly cookie、PostgreSQL／SQLAlchemy／Alembic；開始前核對資料庫環境與新增依賴授權。P3 字幕亦已解除 P2 依賴，但不在此 session 開始。

一次 title mutation 驗收曾未命中預期 assertion（約 66 秒，舊 gate 沒保留錯誤細節）；沒有修改產品行為，補上 gate 失敗診斷後完整重跑通過。初次失敗原因未確定，後續若再次出現須以新增 diagnostics 重現，不能把環境失敗當 mutation 成功。

消費端搜尋：`rg -n 'parse|download|direct|native_formats|VideoService' frontend/app frontend/lib frontend/tests backend/app backend/tests`。結果為 `video-form.tsx`／`lib/video.ts`／browser tests → `main.py` → `VideoService`／worker；backend tests 消費對應 endpoint／service／format／URL policy。E2E 與 mutation 自啟動服務已退出；重新閱讀可依 README 啟動自己的兩個 terminal。
