# P3 字幕與匯出

本階段完成字幕取得、人工優先／自動fallback、語言切換、normalized segments與SRT／VTT／TXT匯出。字幕不保存全文、不使用平台cookies、不呼叫模型；既有影片解析／下載與帳號功能保持。

## 行為與閱讀

`frontend/app/subtitle-panel.tsx` 取得／切換字幕與匯出；`main.py` 驗證request與回應；`downloads.py` 控制worker並取消／收回程序；`worker.py` 用既有GuardedDL；`subtitles.py` 負責track policy、json3／Bilibili JSON／SRT／VTT parser與匯出。

頁面預覽最多100段，三種匯出包含全部。不同時間相同文字保留，overlapping cues保留；SRT／VTT毫秒時間往返，TXT只含逐字稿。來源沒提供可取得字幕與格式不支援分開呈現；來源需要登入時不使用cookies繞過。契約及大小限制見[API文件](api-contract.md)，沿用與重新評估條件見[設計盤點](p3-design.md)。

## 驗收

功能與P3指定驗收完成；2026-10-01 Will因資源不足要求暫缓整套browser重跑，已停止服務，不宣稱完整gates全綠。

- `make check`：Python lint／format、TypeScript、production build通過。
- `make test-integration`：在最終cooperative monitor修正前的快照78項通過（auth16、downloads24、parse8、subtitles24、worker6）；包含10次輕量worker請求與teardown回歸、固定Bilibili converter、來源／request／stdout caps。另10次真fixture請求與teardown診斷通過。
- 最終修正後定向5項通過：`uv run --no-sync pytest tests/test_subtitles.py tests/test_downloads.py -k 'swallows_cancellation or stdout_bound or worker_timeout_disconnect or disconnect_stops_worker'`。新增monitor回歸先出現`SUBTITLE_CLEANUP_POLL_ASSERTION`（polls=2），改cooperative Event後通過（polls=1）。最終版本未再重跑整套backend，保留定向驗證與快照的區別。
- 字幕browser兩項通過：人工預設／自動語言切換、三種檔案實際下載讀回、重複句、mobile overflow；無字幕／502 retry／文字XSS fixtures。
- 桌機與390px手機screenshots已實際檢視，無水平溢出。
- start/end交換mutation已由`SUBTITLE_INTERVAL_ASSERTION`攔下，最終獨立入口`python3 scripts/check-subtitle-mutation.py`再驗通過。
- 整套browser曾有7項通過、MP4 case在parse loading時15秒expect逾時；修正等待HTTP response後的整套重跑尚未取得全綠，且曾再出現parse連線重設。Will要求暫緩後已停止browser／API／Next／臨時PostgreSQL，不增加retries或再重跑。最終cooperative Event修正尚未做browser驗證。
- `make test-mutation`的title browser runner曾碰到90秒wrapper deadline，因此沒有完整11項結果；已改240秒，依Will資源要求未再次執行包含browser的完整入口。資源足夠且Will要求時再補整套browser與完整mutation。

## 問題與處理

| 項目 | 證據／處理 | 閉環 |
|---|---|---|
| F1 VTT合法identifier被誤認註解 | code review發現NOTE-1／STYLE-caption／REGION-42等prefix被startswith略過；改成精確header／comment語法 | `test_subtitles_vtt_reserved_prefix_identifiers_preserved`，review再次確認 |
| F2 disconnect cleanup卡住 | fixture-only task dump顯示worker已結束、cleanup gather等待`Request.is_disconnected`→`BaseHTTPMiddleware.receive_or_disconnect`→AnyIO taskgroup；重複probe卡在第3次 | no-store改純ASGI只攔send，不包receive；同樣10次真fixture請求均完成，獨立review確認；有期限的輕量worker回歸測試 |
| F4 polling吞掉native cancellation | 輕量fixture模擬`is_disconnected` cancel scope吞掉task.cancel；修改前worker完成後monitor仍再次poll，具名回歸失敗（2次） | monitor改request-local Event協作結束，不發native cancellation；回歸通過（1次），最終5項取消／stdout／子程序清理通過，code/design review再確認 |
| stdout超限之後pipe backpressure | 有界reader拒絕後可能仍有unread pipe bytes；Python官方[asyncio subprocess文件](https://docs.python.org/3/library/asyncio-subprocess.html)說明pipe與wait互動 | cleanup先收回reader，再discard剩餘bytes同時停止程序；64KiB／4MiB cap的十倍輸出測試通過 |
| 驗收deadline與來源處理期限不一致 | 字幕browser包含parse＋兩次45秒subtitle操作；原MP4 browser也曾在parse loading時碰到15秒expect | 字幕多步case總期限180秒、來源結果expect45秒；MP4先等待parse response並驗200，再驗格式，總期限180秒涵蓋45秒parse＋120秒download；不增加retries、不放寬產品timeout |
| 高負載下測試wrapper期限 | 實際10次fixture啟動的90秒回歸期限曾逾時；title mutation startup也超過90秒 | cleanup測試用輕量獨立worker排除adapter import成本；title runner給240秒涵蓋兩server startup與test，具名斷言要求保持 |

第一次整體測試在parse處卡住，為取得thread診斷只對自己的pytest送SIGABRT（core limit=0），test wrapper已清理自己的臨時PostgreSQL；沒有殺其他專案程序。初次disconnect child test曾出現macOS killpg PermissionError，單測重跑通過，後續整體既有24個download tests均通過；沒有直接吞掉該錯誤。

## Review與邊界

- code review：F1改1項；F2、stdout cleanup與F4 cooperative monitor變動經另輪唯讀確認，累積ledger無未處理項。
- design review：NO DESIGN FINDINGS；worker、request／response邊界、stateless全文、語言選擇、error policy、純ASGI no-store與匯出已核對，盤點補齊相關機制。改／記／提／駁回均0（非finding的盤點完整度建議已補入表）。
- AGENTS對帳1處：補入字幕worker／export segments規則；其餘路徑與驗收入口維持。
- 未跑：真平台subtitle smoke（P0b獨立授權）、remote CI（`git remote`為空）；未下載新依賴、未commit／push（`git rev-parse --verify HEAD`沒有revision）。P4仍等待D2模型／長字幕、D3額度決定。
