---
name: firefly-cycle
description: Drive the operator's Firefly III gathering run — measure how far behind Firefly actually is from its last statement-derived transaction, slice the backlog into cycles oldest first, and emit a tickable per-cycle checklist of exactly which files to download from which source. Use when the operator asks what needs updating in Firefly, says they have fallen behind, wants a statement checklist, or starts a monthly or catch-up import. Stops when files are on disk; firefly-updater takes it from there.
---

# Firefly Cycle

Read [`docs/skills/firefly-facts.md`](../../../docs/skills/firefly-facts.md), then follow [`docs/skills/firefly-cycle.md`](../../../docs/skills/firefly-cycle.md) exactly: establish the backlog from data, one cycle at a time oldest first, read the pending-entries register, check availability before calling anything missing, then emit the checklist.

Read-only against Firefly. The only write is the tracker issue carrying the checklist. This skill handles no credentials, logs in to nothing, and downloads nothing.
