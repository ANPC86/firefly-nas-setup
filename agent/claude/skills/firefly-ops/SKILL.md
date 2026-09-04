---
name: firefly-ops
description: Entry point for any Firefly III work — spend analysis, budgets, categories, subscriptions, rules, imports, reconciliation. Loads the standing facts about Firefly's API through MCP, the write protocol, and the tier rules that decide what may be delegated. Use whenever household finances, transactions, statements or budgets come up, and before delegating to firefly-updater.
---

# Firefly Ops

Read [`docs/skills/firefly-facts.md`](../../../docs/skills/firefly-facts.md) before doing anything else. It exists so that the conventions of a live install never have to be rediscovered.

## Decide the tier before acting

| Tier | Work | Who | Route |
|---|---|---|---|
| **0 — Gathering** | How far behind is Firefly; which files to retrieve | Operator's hands; `firefly-cycle` drives it | Read-only MCP plus one tracker write |
| **1 — Mechanical** | Import prep, recategorisation from an approved list, a single verified entry | Delegate to `firefly-updater` | MCP only |
| **2 — Analysis** | Spend analysis, budget sizing, reconciliation, data-quality review | Main session | Read-only API; read-only database as a last resort, stated when used |
| **3 — Architecture** | Category and budget taxonomy, rules, account structure | Main session; the operator decides | Writes need explicit per-change authorisation |

Tier 1 is the only tier that delegates. A sub-agent receives a **resolved worklist** — per row: the group id, the expected description and amount, the current value, the target value — never a question of judgment and never raw ids it would have to translate.

## Write protocol

Every step exists because something went wrong without it. All six for a batch; the first three for any single write.

1. **Take a fresh dump first** (`docker exec firefly_iii_backup /backup.sh`). Do not rely on the nightly one.
2. **Read the record back before writing to it.** Confirm description, amount and current value. A mis-targeted write reports success.
3. **Pass only the fields being changed.**
4. **Canary one row, verify, then run the batch.**
5. **Verify independently of the agent that did the work.** Its report is a claim, not evidence.
6. **Check for leaks after any recategorisation** — rows that kept a budget or tag they should have lost. Rules do not clean up after themselves.

Multi-leg splits are the standing exception: edit those in the UI, or leave them.

## Privacy

Raw statements, exports, mappings and anything carrying a real identifier live in gitignored `.local/`. Nothing carrying a balance, an account number or a personal name goes into a tracked file, an issue or a chat that leaves the machine. Statements are sanitized (`sanitize/`) before an assistant reads them.
