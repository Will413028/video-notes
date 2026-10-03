---
title: FastAPI 統一 session、PostgreSQL 與同源 API
project: video-notes
date: 2026-10-01
review-date: 2027-04-01
status: active
tags: [video-notes, decision, authentication, postgresql]
---

# FastAPI 統一 session、PostgreSQL 與同源 API

## Context

從零重做完整影片學習工具，原作只作功能參考。Will 選定由 agent 實作、自己閱讀與修改，並確認採用建議架構。

- `external` Next.js + FastAPI、全部功能含登入與支付：Will 指定。
- `inherited` FastAPI 統一業務判定：計畫不變量；目前仍成立，因會員、額度與支付都由同一後端管理。
- 無既有部署、資料或客戶端 migration；原作 JWT／SQLite 不構成限制。

## Options Considered

- **A（選用／基準）**：FastAPI 管 server-side session，browser 用 HttpOnly cookie；PostgreSQL + SQLAlchemy + Alembic；同源轉送。認證可撤銷、交易與 migration 完整，代價是需要資料庫與 CSRF 保護。[OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)。
- **B**：JWT + SQLite，browser 直接或同源呼叫 API。起步快、接近原作；token 存放、撤銷與高併發資料交易需另外設計。
- **C**：managed auth/DB。省帳號基礎設施，增加帳號、供應商契約與外部設定依賴。
- Routing 可採直連（需 CORS 與跨域 cookie）、同源轉送（需測串流與檔案）、BFF（需維護額外契約與認證層）。P0a 已證明本機 production 同源 rewrite 可行。

## Decision

Will 於 2026-10-01 確認 A：session + HttpOnly cookie、PostgreSQL、同源轉送。Next.js 負責呈現與轉送，FastAPI 負責 auth／quota／payment 的判定，不建立重複的 Next.js 業務層。

## Rationale

相較 JWT／SQLite，這組設計讓後續會員與支付交易落在同一資料層，並能由後端撤銷 session；代價是額外的 DB、migration 與 CSRF 實作。不選 managed auth 是為了在此學習專案掌握完整流程，且目前不需登入外部服務。同源轉送避免跨域配置；仍須保留延遲驗收，hosting/CDN 必須另外測。

## Expected Outcome

- P1 可經 Next.js 同源 API 取得 FastAPI 的解析結果，CI/local 共用入口。
- P3a 完成 server-side session、撤銷、CSRF、PostgreSQL migrations 與安全 cookie 驗收。

## Followup

- P3a 落地 session 安全預設與資料層；已在主計畫，不另建待辦。
- P8／D5 上線前驗證 proxy/CDN streaming 及 secure cookie；已在主計畫。

## Revocation Triggers

- 必須提供第三方 API／原生 app 身份契約時，重新評估 token 模式。
- 目標 hosting 無法轉送 SSE／大檔，重新評估 routing；不變更 FastAPI 的業務 SSOT。

## Review Notes

尚未到 review 日期。

## Related

- 本 ADR 即使用者與 agent 對話當場拍板的原始紀錄，無外部來源文件。
- [主計畫](../2026-10-01-rebuild.md)、[P0a 實測報告](spike/report.md)、[API 契約](api-contract.md)。
- 不抽取通用 Lessons：此檔記錄專案取捨，沒有新增跨專案規則。
