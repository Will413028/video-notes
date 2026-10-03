# P3a：登入與持久化

依 [D1](architecture-decision.md) 使用 PostgreSQL、SQLAlchemy、Alembic 與 FastAPI server-side session；Next.js 僅消費同源 API。沒有既有部署或資料搬移。

## 契約與安全預設

- users：UUID、normalized email unique、Argon2id password hash、created_at。email 不作 provider identity；P3a 不包含 OAuth、email verification、password reset。
- sessions：256-bit 隨機 opaque token，資料庫只存 SHA-256 digest、user_id、created_at、last_seen_at、absolute_expires_at。token 只經 HttpOnly cookie，API 不回傳 token，前端不存 localStorage。
- idle timeout 30 分鐘、absolute timeout 12 小時；成功 `/api/auth/me` 在持有 row lock 的同一交易續期並重發 cookie，絕對期限不延長。登出刪除 session；每次認證查 PostgreSQL，不以 cookie 存在作認證。兩種期限都驗收。
- 每次啟動 API 清理 idle／absolute 已過期 rows，保留活躍 session；使用兩個 expiry index。本機版不引入 scheduler，持續運行時過期 rows 保留到下一次啟動；公開服務前依 P8/D5 補定期清理。
- 本機 cookie `vn_session`、HttpOnly／SameSite=Lax／Path=/／不設 Domain；HTTPS 模式使用 Secure 與 `__Host-vn_session`，設定 origin 必須為 HTTPS，不根據 client headers 判斷環境。
- 所有 auth POST 要求 configured exact Origin、`X-Requested-With: video-notes`、JSON Content-Type；拒絕 missing／null／跨源 Origin。無 CORS allowlist，不允許跨來源 credentialed API；SameSite 是輔助防線。
- 註冊／登入／登出為 JSON POST；me 為 GET。回傳 user id／email；401 表示無有效身份，403 CSRF 拒絕，409 email 已使用；auth response `Cache-Control: no-store`。
- 密碼 15–128 個 Unicode 字元、不裁切或 strip；email normalization 與 schema 驗證分開。Argon2id 19 MiB、2 iterations、parallelism 1。密碼計算在 worker thread，DB route 使用同步 SQLAlchemy（FastAPI threadpool），不阻塞 async loop。
- 登入採通用錯誤與 dummy hash verification；本機有限頻率保護，不宣稱可公開部署。公開服務前必須補跨 instance abuse policy／email verification／帳號恢復，依 P8/D5。
- database URL 若需要憑證只從環境取得，不讀或列印 `.env`。本機驗收由腳本啟動獨占 PostgreSQL cluster，Unix socket 位於專案 ignored runtime；不連線其他現存 DB，不下載 Docker image。
- 不更改 P2 公開 fixture／下載契約；認證依賴先供後續 AI／quota 使用。本階段不把免費解析下載改成必須登入。

## 驗收

- Alembic upgrade／downgrade／upgrade 在隔離 PostgreSQL，schema unique／FK／timezone 與交易真實驗收；不以 SQLite 代替 PostgreSQL。
- register／login／logout／me，wrong password、expired idle／absolute、revoked／forged session、CSRF bypass、duplicate email、session rotation 與 reload persistence。
- Browser→Next rewrite→FastAPI→PostgreSQL 真實註冊／登入／重新整理／登出；cookie HttpOnly／SameSite／host-only；安全設定 fixture 驗 Secure。
- mutation 停用認證查詢／CSRF／過期判斷時，對應測試必須失敗。P2 原 tests／browser／mutations 保持。
- 獨立 code review 與 design-review；完成後附閱讀順序与修改練習。

## 來源

- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

以上為安全預設與當前同源約束的實作；D1 不變。增加 native client、跨源部署或提高 session 期限時重評。
