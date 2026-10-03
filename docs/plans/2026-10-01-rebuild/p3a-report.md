# P3a：登入與持久化

日期 2026-10-01；本機 macOS、PostgreSQL 16.15、Python 3.14.7、Node 26。依賴下載由 Will 在本 session 另次允許；lockfile 安裝 SQLAlchemy 2.0.54、Alembic 1.20.0、psycopg 3.3.6、argon2-cffi 25.1.0。

## 交付

- users／sessions schema 與可往返的 Alembic migration；session digest、timezone-aware timestamps、email unique、FK／expiry indexes。
- FastAPI 註冊、登入、me、登出、撤銷／rotation、idle30分鐘與absolute12小時；HttpOnly／SameSite cookie，HTTPS配置使用Secure與__Host prefix。
- Origin／custom header／JSON CSRF；auth response no-store；validation不含密碼輸入；有限頻率保護、dummy password verification。
- 瀏覽器帳號表單、初始session確認、錯誤與處理狀態；保留P2公開解析下載。
- 本機獨占持久化 PostgreSQL 的 dev-api；隔離臨時 PostgreSQL 的 tests，migration／downgrade只允許隔離驗收環境。

## 證據

| 驗收 | 結果 |
|---|---|
| `make check` | Python lint／format、TypeScript、production build通過 |
| `make test-integration` | 54 passed（16 auth＋38既有）；真實PostgreSQL、migration往返、錯誤密碼、duplicate、撤銷／偽造／idle／absolute過期、續期、CSRF、password redaction、rate limit、expired cleanup |
| `make test-e2e` | 6 passed；browser→Next→FastAPI→PostgreSQL註冊／refresh／logout／login，及5既有影片案例 |
| dev persistence smoke | 真正啟動 dev-api 兩次，重啟 PostgreSQL與API後原user／session有效，最後logout與停止服務；僅本機public fixture帳號，沒有使用既有帳號／憑證 |
| `make test-mutation` | 全部10項通過：既有title＋5 download、4 auth mutations；隔離副本破壞身份、CSRF、期限與validation清理，各由指定失敗攔下 |
| 補驗證 | 最新隔離harness下16 auth cases重跑通過；Secure／__Host／Path／host-only實際response驗證通過；PostgreSQL environment清理後啟停通過 |
| 視覺／vault／diff | 帳號桌面／390px手機截圖實際view_image，無裁切／水平溢出；vault lint／links及自有檔案whitespace／Markdown連結通過 |

輸出在 ignored `check-p3a.log`、`backend/tests-p3a.log`、`e2e-p3a.log`、`backend/dev-smoke-p3a.log`、`mutations-p3a.log`。密碼與session token不列印、不寫回JSON；瀏覽器只持有HttpOnly cookie。

## 審查與修正

- Code F1（已修）：預設FastAPI422會含password input；統一清理成loc／type／msg。短／長密碼案例通過；恢復原handler的mutation確實使2案例失敗。第一次「before」命令在初始化DB後才載入修正版，因此不能當修正前失敗證據；以隔離mutation重現原行為。
- Design DR1（已改）：過期session生命週期未定；每次API啟動清理idle／absolute expired rows，保留活躍session，使用兩個expiry index。本機不引入scheduler，公開服務前依P8/D5補定期清理。
- Code複核：F1與新DB lifecycle無重要殘留；主agent自行重跑，不把review報告當執行證據。Design檢查UUID、digest、DB／threadpool／transaction、CSRF、cookie、rate limit、前端與PG harness；1 finding改1、記／提／駁回0。原作只用靜態盤點，未宣稱逐行對照。
- 原P2 child cleanup test存在readiness race：PID檔先存在、尚未寫入即取消，讀到空字串。改用寫完臨時檔後atomic replace公布PID；54測試通過。沒有放寬取消後child存活斷言。
- Browser test錯把reload後預設login當作register模式；更正操作及重新填email。原5秒expect有解析仍在進行的失敗；wait按API deadline調到15秒、test60秒，保持0 retries。最終6案例通過。
- 本機持久化 smoke第一次HTTP health probe遇ConnectTimeout，driver readiness異常未清理；確認本次Popen的process group lineage後停止，再以trust_env=False與所有startup異常均清理的driver重跑通過。未重用或停止其他服務。

## 執行與閱讀

依 [README](../../../README.md)，兩個terminal執行 `make dev-api`／`make dev-web`。PG工具需在PATH；dev資料在ignored `backend/.runtime-db/`，Ctrl-C停止cluster但保留資料。驗收資料另建臨時cluster，結束清除，不使用dev資料。

閱讀 `account-panel.tsx` → `lib/auth.ts` → `app/auth.py` → `database.py` → `0001_auth.py` → `test_auth.py`。試著改idle期限，追蹤cookie Max-Age與DB時間；看登出後cookie即使重新送回也無法取回user的測試。

CI固定ubuntu-24.04與PostgreSQL16工具路徑；[官方runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)列出PG16.15。remote CI尚未執行，沒有remote。Starlette TestClient的httpx deprecation warning保留，沒有繞過驗收。

本階段沒有外部登入、模型、真平台下載或支付。email驗證／帳號恢復／公開服務abuse policy在P8/D5觸發；不宣稱此本機版本已可公開商用。下一步P3字幕與匯出，不在此階段開始。未commit／stage／push。

消費端搜尋（repo根目錄）：`rg -n 'auth|session|currentUser|/me|database|LoginSession' frontend/app frontend/lib frontend/tests backend/app backend/tests scripts backend/migrations`。結果：AccountPanel→lib/auth→same-origin rewrite→auth router／database dependency／User與LoginSession，tests與PG scripts消費同一契約。指令檔對帳新增auth與隔離DB／build順序規則兩處；沒有將歷史驗收寫成現行規則。`git rev-parse --verify HEAD`確認repo仍沒有commit；status所有產品路徑仍untracked。驗收及本次dev服務均停止。
