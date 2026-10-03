---
title: Agent 分階段實作，Will 閱讀與修改
date: 2026-10-01
status: active
tags: [personal, decision, learning-material]
---

# Agent 分階段實作，Will 閱讀與修改

## Context

Will 要求完整重做影片學習工具，並明確指定「你分階段實作，我閱讀與修改」。從零開始，原作只是功能參考。

- `external`：Next.js + FastAPI、完整功能分階段完成，由 Will 指定。
- `external`：學習分工採 agent 實作、Will 閱讀與修改，由 Will 指定。
- 無須延續原作技術或既有資料 migration 的 inherited 約束。

## Options Considered

- **A／學習基準**：Will 主寫，agent 提供練習、提示及 review。主動練習有利於暴露理解缺口，代價是完整系統推進較慢；參考 [Teaching Tech Together：練習與形成性評量](https://teachtogether.tech/en/index.html)。
- **B／選用**：Agent 每階段交付可執行程式、驗證及閱讀路線，Will 閱讀與修改。較快取得完整範例，代價是閱讀理解不能證明獨立實作能力。

## Decision

採 B。每階段保留功能邊界、閱讀入口與驗證證據，供 Will 修改；功能路線涵蓋登入、額度與 Stripe。

## Rationale

相較主寫模式，Will 選擇先建立完整可運作的系統，再閱讀與修改。代價是需要主動練習驗證理解，不能以 agent 的測試通過當作學習成效。不選 A 是尊重當次明確分工，而非否定主動練習的價值。

## Expected Outcome

每個階段都有可閱讀、可修改、可驗證的成果；是否掌握由 Will 的解釋與修改確認，沒有宣稱目前已達成。

## Revocation Triggers

- Will 改以獨立實作、面試練習或某模組深度掌握為目標時，改為主寫加 review。

## Review Notes

初版；尚未到 review 日期。

## Related

- 本 ADR 即原始紀錄，無外部來源文件；來源為 2026-10-01 Will 與 agent 的分工對話。
- 無新增跨專案 Lessons Rules，學習分工保持專案決策。
