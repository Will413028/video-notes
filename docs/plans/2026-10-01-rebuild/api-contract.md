# API 與 routing 契約

## P1 已定義的薄路徑

- Browser 只呼叫相對路徑 `/api/*`；開發／測試 Next.js 在 127.0.0.1:3422，FastAPI 在 127.0.0.1:8422。
- Next.js rewrite 把原 method、body 與 headers 轉送到設定的 backend origin；origin 只由 server 設定，不接受 client 指定。
- `/api/health` GET：200，`{"status":"ok"}`。
- `/api/parse` POST：JSON `{"url":"fixture://learning-demo"}`；200 回 `id/title/uploader/duration_seconds/source`。P1 只接受此 deterministic 範例，無外部網路 I/O。
- title 為「用 AI 建立你的學習工作流」、uploader 為「video-notes」、duration_seconds=754、source=`demo`；fixture 同時是 browser E2E 的獨立驗收值。
- 未知來源 422；過長／空值／多餘欄位 422。HTTP 錯誤由前端顯示可讀訊息，不顯示 stack trace。
- P1 沒有登入、AI、資料庫、檔案或 SSE 產品 endpoint；它們不是已完成能力。

## P2 擴充

- `/api/parse` 接受 exact-host YouTube／Bilibili 單支影片 URL 與原 fixture。回應新增 `formats`，每列為 `format_id/label/ext/has_audio/requires_merge`；空列表表示目前無原生可下載格式。
- `/api/download` POST：JSON `{url, format_id}`；成功串流 attachment bytes、Content-Length 與 UTF-8 Content-Disposition；準備期失敗 502。Abort／傳輸錯誤／正常完成後清理任務檔。
- `/api/direct` POST：同一 JSON；200 `{url}` 與 `Cache-Control: no-store`，只提供已含音軌的原生格式；需要合併或 fixture 回 502。直鏈可能過期，瀏覽器可複製，但不保證來源允許跨域下載。
- 格式 id 只接受解析出的白名單，server 重新解析後驗證。入口不合法／request validation 422，worker 處理失敗／取消／timeout／size cap 502；只回通用錯誤，不回 provider signed URL 或 traceback。
- 原作範例 title／duration 保持，fixture 下載為另行生成的一秒測試片，與 754 秒 metadata 示範值用途不同。
- 真平台／CDN／DNS／redirect 的實際 socket 只能連 public IP／80／443，限 urllib transport；ffmpeg 不讀遠端 URL。這些防護的 fixtures 已測，真平台 smoke 另需授權。

## P3a 帳號

- `/api/auth/register` POST `{email,password}`：201 `{id,email}` 與 session cookie；duplicate 409。
- `/api/auth/login` POST 同 payload：200 user 與新的 cookie；wrong password／unknown email 統一 401，舊 cookie 對應的 session 撤銷。
- `/api/auth/me` GET：有效 session 200 user，否則401；idle 30分鐘、absolute12小時，認證後同步更新 idle 與 cookie期限。
- `/api/auth/logout` POST `{}`：200 `{status:"ok"}`，刪除 session 與 cookie；idempotent。所有auth POST要求exact configured Origin、X-Requested-With=video-notes、application/json；不滿足403。
- auth responses含錯誤均no-store，validation422不含input／ctx與明文密碼。有限頻率保護429；未設定DB時503，P2公開解析下載保持可用。
- 本機 vn_session；HTTPS配置使用 __Host-vn_session。cookie HttpOnly／SameSite=Lax／Path=/，不設Domain；Secure模式必須HTTPS。註冊即登入，本階段不提供email驗證／密碼找回。

## P3 字幕

- `/api/subtitles` POST `{url, track_id?}`：200 `{status, tracks, selected, segments}`，no-store。tracks 含 `id/language/source`（manual／automatic），選擇 id 例如 `manual:zh-Hant`。不指定時人工優先，再依 language 字典序；指定時只選該軌，不默默切換。
- segments 為 `{start,end,text}`，時間秒、毫秒精度、依 start 排列，允許 cue 重疊；不同時間相同句子保留。markup 轉純文字、空 cue 忽略；非法／逆序時間拒絕，避免靜默修補。json3／Bilibili JSON／內嵌 SRT／VTT 可解析；Bilibili danmaku 不是字幕，排除；`ai-*` 標記 automatic。
- `ready` 表示有字幕；`unavailable` 表示來源未提供可取得字幕或所選軌為空；`unsupported` 表示有字幕但沒有支援的格式。來源要求登入或限制匿名訪問時，不聲稱影片本身沒有字幕；本階段不使用 cookies。
- `/api/subtitles/export` POST `{format:"srt"|"vtt"|"txt", segments}`：200 UTF-8 attachment `subtitles.<format>`，no-store。不再次取得平台字幕、不保存全文；SRT／VTT 保留時間，TXT 只包含逐字稿。格式為標準化純文字，不保留原樣式。
- 字幕來源文字／總 segment text 上限 2 MiB，最多 10,000 段、每段 5,000 字元，時間不超過 100 小時；worker JSON 上限 4 MiB。字幕 request body 8 KiB、export body 4 MiB，解碼前計數（含無 Content-Length）；超過 body 上限 413。request validation 422，worker 取得／解析失敗 502。超過限制不截斷。
- 字幕與影片使用同一組兩個 worker slots、45秒處理 timeout、client disconnect 清理及 public-IP socket 邊界。頁面最多預覽100段，匯出包含全部；每次語言切換重新取得，取消可重試。
- 範例 `fixture://learning-demo` 含 zh-Hant 人工、en 自動字幕與兩段相同句子。平台 adapter 測試使用本機 response fixtures，真平台可取得性仍屬 P0b opt-in smoke。

## 後續部署邊界

- P3a browser credentials 為 HttpOnly session cookie；同源 fetch 明示 `credentials: 'same-origin'`。Next.js 不解碼或自行判定 session。
- FastAPI 設 cookie 不設 Domain，production 用 Secure／HttpOnly／SameSite；CSRF、期限與撤銷契約在 P3a 按 OWASP 預設落地。
- 後續 SSE／檔案透過同一路徑轉送，不整體 buffer；P1 沿用 P0a 的 `compress:false`。上線時 CDN/reverse proxy 另驗。
- 不接受使用者提供任意 upstream URL；影片 URL 的外部訪問安全在 P2 落地。
