# Firefly Cycle — the gathering run

Read [firefly-facts.md](firefly-facts.md) first.

This drives the half of an import that needs the operator's own hands and credentials: working out how far behind Firefly actually is, deciding which cycle to work, and listing exactly what to download from where. It stops when files exist on disk. Everything after that — parsing, mapping, import, readback — is [firefly-updater.md](firefly-updater.md).

## Why this exists

The processing half gets documented first because that is where the expensive mistakes happen. The gathering half lives in the operator's memory and decays between runs: which portal, which export screen, which date range, what the file is called, when it is even published. A month is long enough to forget all of it. The failure this prevents is not a bad import; it is a cycle that never starts, or one that starts against the wrong window and silently leaves a gap.

## What must never be assumed

**The backlog is not "this month."** The rhythm is meant to be monthly; it slips to two, sometimes more. Assuming the current month silently skips whatever fell in the gap, and the gap is invisible afterwards because nothing in Firefly marks an absence. **Compute the backlog from data, never from the calendar.**

## Step 1 — Establish the backlog from Firefly

1. `get_accounts` for `asset` and for `liability`. Record `last_activity` per account.
2. Sweep `get_transactions` from the **earliest** `last_activity` in that set through today. The point is not the rows; it is to separate two things that both look current:
   - **Automated postings.** A workflow that posts rows keeps `last_activity` moving while no statement has been imported. An account can look current and be four months behind. They are recognisable by their poster's signature — description, tags and notes are stable because software wrote them.
   - **Statement-derived rows.** These carry an import-cycle tag naming the source file.
3. For each account the honest figure is the **last statement-derived date**, not `last_activity`. Where they differ, report both and say which is which.
4. Confirm any ambiguous account by querying it directly with an `end` bound and reading the import tag on its newest row.

The backlog is the span from the oldest statement-derived date to today, stated in months.

## Step 2 — Slice into cycles, oldest first

Work **one cycle at a time, oldest first.** The reasons are specific:

- Source files are cycle-shaped, not calendar-shaped. A card statement carries rows from the prior month and consecutive exports overlap. Two open cycles make every boundary row ambiguous.
- Balance continuity is validated at each boundary, which only means something if the preceding cycle is booked.
- A pending entry from cycle N is cleared by the statement of cycle N+1. Out of order, the register cannot be worked.

## Step 3 — Read the pending-entries register

Before generating anything, read `.local/pending-entries-register.md`. For each open entry decide **clear** or **defer** and record the date checked. Do not re-derive a deferred entry. Surface the open count and the age of the oldest. Carry the watch list forward separately; an import must not silently close an investigation item.

## Step 4 — Check availability before calling anything missing

Per-source availability lives in `.local/source-register.md` (which portal, which screen, which export, file name pattern, publication day). An account whose statement is not yet published is **not** behind. Two distinctions worth repeating from the updater procedure: a mid-month import date is usually a cycle boundary, and an account with only withdrawals across a known payment window is missing the *payment file*, not the statement.

## Step 5 — Emit the cycle checklist

One tracker issue per cycle, titled for the cycle it covers. The body carries, as task boxes grouped by institution:

- one box per file to retrieve, named as the source register says it will be named;
- a box for each pending entry this cycle should clear, with its reference;
- the watch-list items carried in;
- the backlog figure and how it was measured;
- a definition of done.

Task boxes rather than a table, because the operator ticks them as the run progresses and a run is rarely finished in one sitting.

## What this skill does not do

It does not log in to anything, download anything, or handle a credential. It does not parse or import. It produces a measured backlog and a checklist; the operator does the retrieval; the updater takes it from there.
