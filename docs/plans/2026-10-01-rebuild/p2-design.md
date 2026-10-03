# P2：下載實作邊界

- 保留 deterministic 範例與 P1 title 契約；擴充 formats、download 與 direct URL。
- 入口只接受 YouTube、youtu.be、Bilibili、b23.tv 的 exact hosts，HTTP(S) 與預設連接埠；拒絕帳密、IP literal、控制字元與其他 scheme。抖音由 P7 專用適配。
- 每次真實解析／下載啟動獨立 Python worker，yt-dlp 固定版本；不讀外部 cookies／config／proxy／plugins，不下載 JS runtime。
- worker 強制 urllib transport；在 socket 邊界驗證並使用 public IP，含 redirect／CDN／DNS 重綁。其他 transport、external downloader、串流 manifest 暫不作 P2 的可選格式；ffmpeg 只合併已下載本機檔。
- UI 只列 HTTP(S) 原生可下載的 muxed 或可本機合併格式，不接受 client 傳入任意 yt-dlp format selector。
- 下載檔在每任務 UUID 目錄；取消／失败／傳送完成必清理。啟動時以 process lock 保護獨占 root，再清除服務自己的孤兒目錄；其他檔案不碰。
- worker 有總 timeout（解析 45 秒／下載 120 秒）、128 MiB 預設成品／來源總和大小上限（`VIDEO_NOTES_MAX_DOWNLOAD_BYTES`）與 2 個任務上限；下載 slot 保留到傳輸完成。合併期間來源與成品會共存，parent 每 50 ms 監控暫存預算 2 × 上限 + 1 MiB，超過即終止 process group；輪詢期間可有短暫超量。其環境為本機學習版，不代表已可商用公開。
- fixture download 用既有 ffmpeg 生成短片與音軌；CI 使用可重跑 fixture，不訪問真平台。真平台 smoke 需要使用者另次授權與來源。

沿用盤點：yt-dlp 因平台適配的成本而保留；同步直接呼叫改為子程序，為了取消與網路防護；原作 title 命名暫存改為 UUID；下載前重新解析並驗證 format；Next.js 同源轉送沿用已實測的 P0a。

設計審查：前端保留 fetch → Blob，方便取消與顯示傳輸進度；瀏覽器必須在記憶體持有整支影片。本機 128 MiB 上限下接受這項取捨，提高上限或改公開服務時改評估受控任務 URL 與 browser 原生下載。yt-dlp 的 `_request_director`／`format_selector` 與 socket guard 是固定版本適配邊界；升級時必須重跑選定格式、實際 transport、私網阻擋、下載與合併測試。
