# Firefly Updater — the import-preparation procedure

Read [firefly-facts.md](firefly-facts.md) first.

This procedure turns a statement that is already on disk into import rows the Data Importer can take, and diagnoses an unexpected import result. It **applies** rules; it does not invent category policy or account structure. It starts where files already exist — getting them there is [firefly-cycle.md](firefly-cycle.md).

It is written for one Firefly install but the shape is general: resolve against live data, validate continuity, apply only deterministic rules, hold the rest, give every row a stable identity, verify after import by reading back.

## Privacy, first

- Raw statements, generated CSVs, mappings and anything carrying a real identifier live in a gitignored `.local/`. Nothing from them appears in a tracked file, an issue, or a chat transcript that leaves the machine.
- A statement an assistant reads has been through [`sanitize/`](../../sanitize/) first. The assistant works on pseudonyms; the mapping back to real identifiers is applied on the operator's side, in `.local/`.
- Never print tokens, account numbers, or raw environment files. Never execute database, SSH or container commands as part of normal work; a direct-database path is an operator-managed break-glass step that needs explicit confirmation naming its exact scope.

## Before a new cycle

Read the retrospective of the last one. Every install accumulates rules that exist because something went wrong; three that recur:

- **Interest on a line of credit is two real, non-duplicate legs**: an accrual (liability → interest expense) and a cash settlement (bank → liability). Generate and validate both. Do not deduplicate one against the other.
- **Before importing a newly added account or card, query Firefly for already-recorded counterparty-side rows** matching the proposed row's date, amount and direction. A confirmed match is paired with the existing row or skipped with provenance; an ambiguous one goes to `HOLD-review.csv`. Do not create a second payment leg because it appears on the new statement too.
- **Check statement-cycle boundaries.** A card file named for a month can contain the prior month's rows and overlap the previous file. Compare every out-of-period row with the target account's live history before generating it. The importer's duplicate detection is not sufficient when dates differ.

## Established payee rules — the template

Rules are written per payee, deterministically, and re-checked against live data each cycle. The shape of a good rule, with fictional examples:

- **Same utility, two properties.** Before categorising a charge from *Utility Co*, read the live subscriptions for it and compare the amount against each subscription's min/max band. The band identifies the property. If no band matches, or the bands overlap for this amount, the row goes to `HOLD-review.csv` with the reason. Do not classify from the payee text alone.
- **Small fixed-band municipal charge = transit.** *Municipality* charges in the transit fare band map to the transit payee and *Transportation*. Any other amount from the same municipality needs property or service context and goes to HOLD.
- **A bill paid for someone else is support, not a utility.** *Telecom – Parents* is *Family Support*, not a household utility and not a business line, regardless of what the description says.
- **Cashback is income.** A card's cashback credit is a deposit from a *Card Cashback* revenue account, never a card→cash transfer.
- **Pay-in-full prepaid card**: the funding transfer is booked once, from the funding account's statement; the card-side row of the same movement is excluded.
- **Airline charge with no business context = personal travel.** Use *Personal Travel*; use a catch-all only if the operator says so.

Write your own in this form: payee → the live data to consult → the deterministic mapping → what sends it to HOLD.

## Pending-entry register

A cycle regularly ends mid-event: the itemisation is known but the card charge has not posted, or a payment leg belongs to a card whose statement has not arrived. Such an entry is **fully resolved** — it is not a HOLD row, which is one whose mapping is ambiguous — and it must not be invented by guessing a posting date. Guessing produces a permanent duplicate when the real statement lands; deferring produces a visible, self-correcting gap.

Record every such event in `.local/pending-entries-register.md`: what it is, which statement unblocks it, the exact entry to make, whichever leg is already booked, and the effect on balances while it stays open. **Read the register at the start of every cycle, before generating any rows**, and for each open entry decide *clear* (the blocking statement is in scope; post it, verify against the statement, move it to Closed) or *defer* (update "last checked"; do not re-derive). Surface the open count when reporting.

Keep a separate **watch list** in the same file for open questions needing investigation — balance variances, suspected unbooked recurring income, rows no rule covers. Those are not pending entries and an import must not silently close one.

### Statement availability

An account whose statement has not been published yet is **not** behind. Keep a per-source table of when each statement becomes available (day of month, or "cycle file, cutoff varies") and check it before opening a pending entry, reporting an account as behind, or investigating a variance.

Two distinctions that have each cost a wrong conclusion: a card imported through a mid-month date is usually at its **cycle boundary**, not incomplete; and an account holding only withdrawals across a window where a payment is known to have occurred is missing the **payment file**, not the statement — the usual symptom is a credit-card asset showing a positive balance.

## Prepare a safe import

1. Keep raw statements, rulesets, generated CSVs and importer configs in `.local/`.
2. Parse the statement and **validate balance continuity at every date boundary** before trusting anything downstream. For a card: `previous balance − payments − credits + interest + purchases + fees = new balance`, and each statement's previous balance equals the preceding one's new balance.
3. Apply deterministic payee rules only. Unknown or ambiguous payees go to `HOLD-review.csv` with an explanation. Do not guess.
4. Give every output row a **unique, human-legible `notes` value that includes its source-row reference** (`source=<file>#data-row-N`). This is what stops the importer's duplicate detection from skipping a legitimate same-day, same-amount pair.
5. Use **signed amounts** for direction: negative leaves the owning account, positive arrives. Map the importer's `type` role to `_ignore`.
6. **Split files by owning statement account**; an importer run has one default account. Map the owning account to the `account-id` role on every row — deposits, refunds and transfers included — and the counterparty to `opposing-id`. Validate the resulting source and destination through a one-row readback before trusting a batch.
7. **Check every resolved payee name for multiple account types.** A name that exists as both an expense and a revenue account needs the expected type and id stated before a row is generated. Re-run this collision scan from live data each cycle.

Card statements that are cycle files rather than calendar files: treat the file's posted-date range as authoritative for row identity, compare every row in the boundary range with the owning account's live history, hard-skip confirmed matches into a cycle `SKIP` register with the source reference, and HOLD anything with more than one plausible live match. The importer's duplicate detection is not the boundary decision.

## After the import: verify by readback

Treat a successful-looking importer result as unverified until the created rows have been read back through MCP and compared on type, date, absolute amount, source, destination, description, category, notes and tags. The importer may append its cycle tag to every row; source tags are a required subset, and only unexpected or missing tags are discrepancies.

## Diagnose and remediate

When a corrected re-import is blocked by duplicate detection, in this order:

1. **Correct the existing transaction in place** through MCP, when that preserves the intended economic event.
2. If a replacement is necessary, give it a **new, stable, source-derived note**. This is a new import candidate, not a way around duplicate protection: first verify through MCP that the original is absent from normal views, that the proposed row is exactly one intended event, and that no matching live counterparty-side row exists. Then explicit operator approval, a bounded sample, readback.
3. If neither is safe, stop and hand back a bounded, human-only break-glass request naming the exact transaction scope. The assistant does not execute that path.

## Report

Generated paths; row counts by disposition (premapped, HOLD, SKIP); the balance-continuity result; the validation sample; the source timestamp; open pending entries; remaining ambiguity. A prepared CSV is not an imported transaction, and the importer's completion screen is not verification.
