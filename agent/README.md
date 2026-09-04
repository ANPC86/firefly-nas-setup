# Letting an AI assistant work in Firefly III

Once the MCP server from [`compose/firefly-mcp`](../compose/firefly-mcp/) is up, an assistant can read every account, transaction, budget and subscription. That is the easy half. The half that goes wrong with a bare "here are 140 tools" setup is anything that *writes*: an update aimed at the wrong of Firefly's two transaction ids, a liability payment proposed as a transfer that the API rejects, the same interest charge deduplicated out of existence because it appears on two statements, a card statement's gift-card line booked as an expense. The files here turn that into a bounded, checkable procedure, and — just as important — into a **gathering** procedure, so the monthly import actually starts.

```
agent/
├── docs/firefly-facts.md                 what Firefly's API does through MCP that will surprise you — read first
├── docs/firefly-cycle.md                 the gathering run: measure the backlog, one cycle at a time, emit a checklist
├── docs/firefly-updater.md               the import-preparation procedure: validate, map, hold, import, read back
├── claude/skills/firefly-ops/SKILL.md    Claude Code entry point: tiers, write protocol, privacy
├── claude/skills/firefly-cycle/SKILL.md  Claude Code skill wrapping the gathering run
├── claude/agents/firefly-updater.md      Claude Code sub-agent for the mechanical import work
└── prompt/firefly-updater-system-prompt.md   the same rules as a system prompt for any other LLM
```

The procedures are the product; the Claude and prompt files are thin wrappers that point at them.

## Before any of this: sanitize

An assistant should never see a raw statement. Run every PDF through [`sanitize/`](../sanitize/) first — with a names file — and hand the assistant the `.sanitized.md`. The procedures below assume that has happened; the updater agent is told to stop if it sees a personal name or an account number in its input. See the [sanitize README](../sanitize/README.md); it is the most important page in this repository.

## What the procedures enforce

- **Nothing is written without an explicit go-ahead** for that exact change. Prepare, validate, show, wait.
- **Two ids, one of them right.** The MCP `id` is the transaction *group*; a journal id fed to an update hits a different record and reports success. Every targeted write is preceded by a readback that confirms description and amount.
- **Liabilities are paid by withdrawal, refunded by deposit**, never by transfer. The API enforces it; the procedure anticipates it.
- **Balance continuity before mapping.** A card statement that does not reconcile is not imported.
- **Deterministic rules only.** Anything ambiguous is a HOLD row with a reason, not a guess. Rules that depend on live data (which property a utility charge belongs to) consult that data every time.
- **Every row has a stable identity** — a note with its source file and row — so legitimate same-day, same-amount pairs survive duplicate detection and every imported row can be traced.
- **Pending entries are recorded, not invented.** A cycle that ends mid-event writes a register entry that the next cycle clears; it does not guess a posting date.
- **Verify from the record.** After import, read the rows back and compare; the importer's completion screen proves nothing.
- **The backlog is measured, not assumed.** The gathering skill computes how far behind Firefly is from the last *statement-derived* row per account, because workflow-posted rows keep `last_activity` current while no statement has been imported for months.

What you do not get: category policy invented on the fly, account structure changed by an agent, a database touched, or any write you did not say yes to.

## Walkthrough — a month-end, illustrated

Synthetic figures, generic institution labels. The operator has fallen behind.

**You:** What do I need to do to bring Firefly up to date?

**Claude (firefly-cycle):** *[`get_accounts` asset and liability; `get_transactions` from the earliest `last_activity`]*

Backlog measured from statement-derived rows, not `last_activity`:

| Account | `last_activity` | Last statement-derived row (import tag) | Behind |
|---|---|---|---|
| Traditional Bank – Savings | 2026-09-01 | 2026-07-31 (`bank-savings-202607`) | 1 cycle |
| Charge Card | 2026-08-24 | 2026-08-24 (`charge-card-202608`) | current |
| Traditional Bank Visa | 2026-08-20 | 2026-07-19 (`visa-202607`) | 1 cycle — the 20 August rows are workflow-posted |
| Online Broker – Cash | 2026-08-31 | 2026-08-31 (`broker-cash-202608`) | current |
| Rental Property HELOC | 2026-08-13 | 2026-07-14 (`heloc-rental-202607`) | 1 cycle |

Backlog: **one cycle, August 2026.** Pending-entries register: 2 open, oldest 34 days (a marketplace order awaiting its card posting; a benefits reimbursement awaiting the savings statement). Availability: the Visa statement for the August cycle publishes on the 9th, so it is available; the charge card is at its cycle boundary, not incomplete.

Checklist issued as tracker issue *Firefly cycle 2026-08*:

- [ ] Traditional Bank — savings account CSV, 2026-08-01 to 2026-08-31
- [ ] Traditional Bank — Visa statement CSV, cycle ending 2026-08-19
- [ ] Traditional Bank — HELOC statement PDF, cycle ending 2026-08-14
- [ ] Clear pending entry P-031 (marketplace order 702-4471) from the Visa file
- [ ] Clear pending entry P-032 (benefits reimbursement) from the savings file
- [ ] Watch list carried: savings interest looks unbooked since May — investigate, do not import over it

**You:** *[downloads the three files into `.local/2026-08/`, runs each PDF through `sanitize/`, ticks the boxes]* Prepare the Visa import.

**Claude (firefly-updater):** *[reads `.local/2026-08/visa-202608.sanitized.md`; `get_account` for the Visa; `get_bills` for the utility bands; `search_transactions` around the boundary]*

Balance continuity: previous balance − payments − credits + purchases + fees = new balance, **reconciles to the cent**; previous balance equals the July statement's new balance.

Boundary check: two rows dated 18–19 July also appear in the July file; both already exist (ids `…4a10`, `…4a12`). **SKIP**, recorded with source refs.

Mapping: 41 rows. 38 deterministic. 2 to HOLD: a municipal charge outside the transit band (property tax or a permit? needs context), and a restaurant with no business marker (personal dining unless you say otherwise). 1 pending entry cleared: order 702-4471 posted on the 10th for 213.55 — matches P-031's itemisation of 149.99 + 38.56 + 25.00; the card line goes to *Marketplace Clearing* and the three itemised rows come out of it.

Files written under `.local/2026-08/`: `visa-202608-premapped.csv` (38 rows), `visa-202608-HOLD-review.csv` (2), `visa-202608-SKIP.csv` (2). Every row's note is `source=visa-202608.csv#row-N`. Nothing has been imported.

**You:** Municipal charge is a dog licence, Personal Misc. Restaurant is personal. Import.

**Claude (firefly-updater):** Both moved to premapped (40 rows). Import is done in the Data Importer's UI with `fidi-visa.json`; I do not run it. When it finishes, tell me and I will read back.

**You:** Done.

**Claude (firefly-updater):** *[`get_account_transactions` for the Visa, 2026-07-20 to 2026-08-19; client-side filter; compare]*

40 rows read back; 40 match on type, date, amount, source, destination, description, category and notes. Tags: source tags present on all 40; the importer added `visa-202608` to each, as configured. Pending entry P-031 moved to Closed with the group id. The HELOC statement is next; it will carry both interest legs.

## Setup — Claude Code

```bash
# 1. MCP server (per project). The bearer is a Firefly Personal Access Token.
claude mcp add --transport http fireflyiii http://<nas-ip>:8490 \
       --header "Authorization: Bearer <firefly personal access token>"

# 2. Skills, agent and docs into your project
mkdir -p .claude/agents .claude/skills docs/skills .local
cp    agent/claude/agents/firefly-updater.md     .claude/agents/
cp -r agent/claude/skills/firefly-ops            .claude/skills/
cp -r agent/claude/skills/firefly-cycle          .claude/skills/
cp    agent/docs/firefly-facts.md agent/docs/firefly-updater.md agent/docs/firefly-cycle.md  docs/skills/
echo ".local/" >> .gitignore
```

Then, in a Claude Code session in that project: `/firefly-ops` loads the standing facts and the tier rules; `/firefly-cycle` measures the backlog and emits the checklist; asking for the `firefly-updater` agent on a sanitized statement produces the premapped, HOLD and SKIP files and, after you import, the readback.

The agent definition restricts the sub-agent to the MCP read tools plus `create_transaction`, `update_transaction` and `delete_transaction`, and to file tools for `.local/`. It cannot reach accounts, budgets, rules or bills administration. Keep `MCP_READ_ONLY=true` on the server until you have watched the write gate hold.

## Setup — any other LLM

Give the model [`prompt/firefly-updater-system-prompt.md`](prompt/firefly-updater-system-prompt.md) as its system prompt and connect it to the same MCP server. The prompt carries the same rules; what it cannot carry is the tool allow-list, so run the server with `MCP_READ_ONLY=true` until you trust the model's write discipline, and prefer a client that lets you disable tools you do not want reachable.

## Adapting

The procedures are written for a Canadian household — a rental property, a self-employment schedule, sales tax collected on invoices — but the structure does not depend on that: measure, gather, validate continuity, map deterministically, hold the rest, give every row an identity, import, read back. Change the payee rules and the tax-form tags; keep the shape.
