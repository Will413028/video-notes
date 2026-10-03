# P1：Walking skeleton 驗收

日期：2026-10-01；本機 macOS arm64、Node 26.10.0、Python 3.14.7、pnpm 11.2.2、uv 0.12.19。

## 交付

- 獨立 Git main 已初始化，尚無 commit／remote。
- Next.js App Router + TypeScript 頁面，輸入／帶入範例、解析中、失敗、重試、結果呈現與手機版。
- FastAPI `/api/health`、`/api/parse`；deterministic parser，沒有外部影片或模型呼叫。
- 同源 rewrite、`compress:false`、API 契約與 D1 ADR。
- CI workflow 與 local 共用 Makefile 入口；pnpm／uv lockfile。

## 驗收結果

| 檢查 | 命令／證據 | 結果 |
|---|---|---|
| Python lint/format、TypeScript、production build | `make check` | 通過 |
| API／输入驗證 | `make test-integration` | 8 passed |
| 真實 browser→Next.js→FastAPI | `make test-e2e` | 3 passed：標題、未知來源後重試、390px 手機版無水平溢出 |
| 標題映射 mutation | `make test-mutation` | 通過；隔離副本回200與title-removed，再由指定 browser heading assertion 失敗 |
| 無 .next 的 typecheck | 附件內暫存 frontend 副本，排除 .next/node_modules/cache，再連結已安裝 node_modules；`pnpm typecheck` | 通過；副本已清除 |
| 視覺 QA | browser 截圖 desktop.png/mobile.png；實際 view_image | 文字、按鈕與卡片無裁切，桌面／手機布局可讀 |
| second-brain gates | lint-rules.py、check-links.py | 通過；此 repo 的本機 Markdown 連結另外核對 |

測試中的 browser 由 Playwright 1.63.0 使用既有 Chromium cache；未下載新 browser。frontend 缺少的型別套件下載由 Will 單次授權，backend 使用 offline cache。

## Source review 與修正

- F1：原 mutation gate 用文字找標題可能假通過；改讀 JSON reporter，只接受唯一指定標題斷言的失敗。先驗證 mutation API 回200與已改標題。復核與實際 mutation 通過。
- F2：README 缺 P1 啟動與驗收指南；已補兩 terminal、依賴、四個 gate、fixture 與閱讀練習。復核通過。
- 測試 role alert 與 Next route-announcer 撞名；限定在影片解析 region，3 個 browser case 通過。
- clean checkout 無 Next 生成型別；typecheck 改為先 next typegen，隔離副本通過。

## 消費端與差異核對

搜尋命令（repo 根目錄）：`rg -n '/api|health|parse' frontend/app frontend/lib frontend/tests backend/app backend/tests`。

結果：frontend/lib/video.ts fetch → app/video-form.tsx 消費；frontend/tests/parse.spec.ts 是 browser caller；frontend/next.config.ts 為 proxy；backend/app/main.py 定義 endpoints，backend/tests/test_parse.py 消費。Git 新 repo 所有檔案尚未追蹤；以 `git status --porcelain --untracked-files=all` 與新檔 diff 核對，本次沒有 commit、stage 或 push。

驗收服務已正常退出；交付時另外啟動 production demo（Next.js 3422、FastAPI 8422），page／同源 health／parse 皆實測200。閱讀完成後可停止這兩個自啟動程序；再次執行 E2E 前需先停止它們。

## 未驗證與下一步

- GitHub remote CI／Linux + Node24 未跑：尚未建立 remote；本機用 CI 相同 make 入口驗收。
- Starlette TestClient 在 httpx 0.28.1 下有 deprecation warning，8 tests 已通過；尚未遷移 httpx2，不隱藏 warning。
- 真平台下載、字幕、AI、登入／PostgreSQL、支付屬後續階段，不能把此 fixture 頁面當作已完成的下載器。
- 下一步 P2：URL policy、yt-dlp adapter、格式／下載、暫存與取消清理；依計畫與必要的新增下載授權開始。

閱讀入口見 [README](../../../README.md)。
