---
title: FastAPI Session、PostgreSQL 與同源 API
date: 2026-10-01
status: active
tags: [personal, decision, fastapi, postgresql]
---

# FastAPI Session、PostgreSQL 與同源 API

## Context

Greenfield browser 學習工具，Will 已確認 server-side session、PostgreSQL 與同源方案；原作不是需要相容的部署。

- `external`：Next.js + FastAPI、登入／額度／Stripe 分階段完成，由 Will 指定。
- `inherited`：agent 實作、Will 閱讀修改；仍成立，因 Will 持續要求按階段交付。
- 原作 JWT／SQLite 與已完成 spike 不限制選型；FastAPI 業務 SSOT 是本次決策，不用作自證約束。

## Options Considered

**認證**

- **A／browser 基準、選用**：Opaque server session + HttpOnly cookie。撤銷直接；代價是 session store、到期清理與 CSRF 防護。[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)。
- **B**：JWT，可搭 PostgreSQL，也可存 HttpOnly cookie。適合多 client／分散驗證；撤銷、refresh rotation、金鑰管理需另設計，cookie JWT 仍須防 CSRF。
- **C**：Managed auth，亦是 greenfield 商用常見方案。減少身份生命週期維護；增加供應商設定、費用與契約，FastAPI 仍須管理額度及支付授權。

**資料庫**

- **D／選用**：PostgreSQL + SQLAlchemy + Alembic。提供共享 store 與明確交易／約束，方便學習並行額度及 webhook 去重；代價是 DB 服務與 migration 維護。
- **E**：SQLite 也有交易，適合單實例、低寫入量；多實例共享與寫入競爭需另評估。[SQLite 適用情境](https://www.sqlite.org/whentouse.html)。目前沒有已證明的流量需求迫使排除 E。

**Routing**

- **F／選用**：Next.js 同源轉送，簡化 browser cookie／CORS；需驗部署環境的串流、timeout、body size 及 headers。
- **G**：Browser 直連 FastAPI，減少轉送層；增加跨來源認證配置。
- **H**：Next.js BFF，可提供 SSR 或前端專用 aggregation；增加契約及身份邊界維護成本，本階段沒有這項需求。

## Decision

採 A + D + F。Next.js 管 UI 與轉送，FastAPI 統一 auth／quota／payment 判定；不在 Next.js 複製業務政策。

## Rationale

目前唯一已知 client 是 browser，session 撤銷模型直接；不選 JWT 是沒有跨 client 驗證需求，而非 JWT 無法支援支付。相較 managed auth，已確認的方案提供可閱讀的登入實作；代價是自行維護安全與帳號流程，並不表示 MFA、OAuth 或密碼恢復已納入範圍。

PostgreSQL 是為學習共享資料與並行交易模型接受的運維成本，不宣稱 SQLite 沒有交易或目前流量已超過其能力。同源轉送降低跨域設定；FastAPI 集中授權避免兩處政策漂移，BFF 若有實際 SSR 需求仍可重新評估。本機 production spike 只證明本機可行，不能外推 CDN／hosting。

## Expected Outcome

- Browser session 可由後端撤銷，安全 cookie、CSRF 及 migrations 有驗收。P3a 已完成本機實作與測試。
- 身份、額度與支付共享明確資料層；後兩者仍待後續階段，尚未宣告完成。

## Followup

- D2／D3 決定後落地額度扣用、失敗處理與並行／冪等契約；同步專案 Pending。
- D4／D5 決定後驗 Stripe webhook 去重及正式 proxy/CDN、Secure cookie；同步專案 Pending。

## Revocation Triggers

- 新增 native app／第三方 API／跨產品身份時，重評 token 或 provider。
- 身份維護需求超出學習投入，重評 managed auth；帳號恢復與 MFA 不自動承諾自行實作。
- Hosting 不支援串流或大檔，重評 routing；SSR 身份需求出現時重評 BFF 邊界。
- 長期確定單實例且 DB 運維妨礙學習，重評 SQLite。

## Review Notes

初版；兩份獨立草稿提出的 JWT／DB 解耦、SQLite 交易、managed auth 與部署限制已納入。

## Related

- 本 ADR 即原始紀錄，無外部來源文件；來源為 2026-10-01 使用者與 agent 的架構確認對話。
- 無新增跨專案 Lessons Rules。
- Repo 的既有架構紀錄 `docs/plans/2026-10-01-rebuild/architecture-decision.md` 仍保留；此 ADR 自含選項與理由。
