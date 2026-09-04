# Firefly III on a NAS

Self-host [Firefly III](https://github.com/firefly-iii/firefly-iii) on a home NAS with a chart of accounts that holds up under real use — several banks, an online broker, credit cards, a mortgage, two lines of credit, a rental property — and connect an MCP server so an AI assistant can read it and, under a bounded procedure, help keep it current.

No real balances, account identifiers, institution names or personal names appear anywhere in this repository. Every account is a generic label for what it *is* (*Traditional Bank*, *Online Broker*), every figure in the fixtures is invented, and the screenshot tool rewrites the page before it captures anything.

Scope: a working setup path with the parts that are not obvious from the upstream docs written down — compose files, first run, the cron caller everyone forgets, a taxonomy that took a year to settle, what subscriptions and budgets are actually for, an MCP server, and a gathering-and-import procedure for an assistant.

---

## ⚠️ Read this first: never hand an assistant a raw statement

Everything in this repository that involves an AI assistant assumes one thing has already happened: **the document it reads has been sanitized on your machine, with a names file, before it goes anywhere.**

A bank or brokerage statement carries your legal name, account and card numbers, address, phone number and sometimes your national identifier. A cloud model does not need any of that to categorise a transaction or draft an import row — it needs dates, amounts, and merchant names. Sending the rest is a leak with no upside. And a PDF with black boxes drawn on it is **not** redacted: the text is still in the file.

[`sanitize/`](sanitize/) contains a script that extracts a PDF's text, replaces identifiers with stable pseudonyms (`[ACCT-7f3a]` stays `[ACCT-7f3a]` on every page), throws the PDF container away, and re-scans its own output. The part that matters most is the **names file**: patterns catch account numbers, but only you can tell the script that *Homer Simpson* is you and *Evergreen Terrace* is your street.

```bash
cp sanitize/pii-names.example.txt .local/pii-names.txt     # then replace every fictional entry with your own
python sanitize/sanitize_pdf.py statement.pdf --names .local/pii-names.txt --strict
# read statement.sanitized.md BEFORE you paste it anywhere
```

Full instructions, the trust model and what the script cannot do: [`sanitize/README.md`](sanitize/README.md). The same kit ships in the companion [ghostfolio-nas-setup](https://github.com/ANPC86/ghostfolio-nas-setup) repository for brokerage documents.

---

## 0. Hardware and platform

Measured on the reference setup, not taken from a spec sheet.

| | Reference setup | Minimum that would work |
|---|---|---|
| Host | **UGREEN DXP4800 Plus** (Intel x86-64, 6 threads, 40 GB RAM) running UGOS Pro (Debian 12 base) with Docker 29 | Any x86-64 or arm64 machine that runs Docker Compose — a NAS with a Docker app, a mini PC, a Raspberry Pi 4/5 with 4 GB |
| RAM, steady state | Firefly core **~130 MB**, MariaDB ~160 MB, Data Importer ~40 MB, MCP server ~180 MB, cron and backup sidecars ~10 MB each | 1 GB free for the stack |
| Disk | Images ~2.2 GB (`core` 920 MB, `data-importer` 810 MB, `mariadb` 330 MB, `fireflyiii-mcp` 185 MB); the database is small — ~210 MB on disk after 18 months and ~2,200 transactions, daily dumps ~0.7 MB compressed | 5 GB |
| CPU | Idle; brief bursts on import, rule runs and the daily cron | 2 cores |
| Network | None required outbound for core use; the importer can reach bank APIs if you enable that flow. No inbound ports for LAN use | — |

A UGREEN NAS with Docker is the suggested route if you are buying hardware for this: the Docker app is built in, the box is on all day anyway, and it can hold the backup sidecar, the reverse proxy and the MCP server. Nothing here is UGREEN-specific.

---

## 1. Setting up Firefly III

Verified against Firefly III **6.6.6** and Data Importer **2.3.4** (2026-09-03). Upstream's own instructions are in the [Firefly III documentation](https://docs.firefly-iii.org/); what follows is the shorter path plus the gotchas.

### 1.1 Compose stack

[`compose/firefly/`](compose/firefly/) is a ready-to-run stack — Firefly III, MariaDB 11.4 LTS, the Data Importer, a **cron caller**, and an opt-in daily dump sidecar — derived from upstream's `docker-compose.yml` with pinned tags. Copy `.env.example` to `.env` and fill in three secrets:

```dotenv
APP_KEY=<exactly 32 random characters>         # forever: it encrypts fields in the database
STATIC_CRON_TOKEN=<exactly 32 random characters>
DB_PASSWORD=<random>
APP_URL=http://<nas-ip>:8080                   # what your browser uses; https://... behind a proxy
```

```bash
cd compose/firefly && cp .env.example .env    # edit the values above
docker compose --profile backup up -d         # omit --profile backup to skip the dump sidecar
curl -f http://localhost:8080/health          # OK
```

Things worth knowing before the first `up`:

| Topic | What to do | Why |
|---|---|---|
| `APP_KEY` | Generate a real 32-character value **before** first start. | It encrypts data at rest. Change it later and encrypted fields become unreadable. |
| **Cron** | Keep the `cron` service, or call `/api/v1/cron/<token>` daily yourself. | Firefly has no internal scheduler. Recurring transactions, **auto-budget limits**, bill warnings and webhooks fire only when something calls that endpoint. The reference install ran five months with budgets configured and no limit ever created. |
| Data Importer token | Leave `FIREFLY_III_ACCESS_TOKEN` empty on first start; create a Personal Access Token after your first login (Options → Profile → OAuth), put it in `.env`, `docker compose up -d importer`. | The token cannot exist before the first user does. |
| MariaDB | Pin the LTS line (`11.4.x`). `MYSQL_RANDOM_ROOT_PASSWORD` means there is no root credential to leak. | The client inside the container is `mariadb`, not `mysql`. |
| Backups | Run the dump sidecar; put `./backups` on a different disk than `./db`. Take a manual dump (`docker exec firefly_iii_backup /backup.sh`) before any batch write. | A logical dump is also what stands up a reporting clone without touching production. |
| Auto-update | Exclude these containers from any auto-update feature. | The importer tracks the core's API; the MCP server reads the same API. Move all three together. |

### 1.2 First run

1. Open `http://<host>:8080`, register. The first user is the admin. Set your primary currency and time zone.
2. **Create the asset and liability accounts before anything else.** Liabilities need their type (mortgage / loan / debt) and direction at creation, and the MCP `create_account` tool cannot set those, so do it in the UI. [`docs/taxonomy.md`](docs/taxonomy.md) is the list.
3. **Create subscriptions and accept their auto-rules** before importing any history, so the rules link transactions in one pass. [`docs/subscriptions-and-budgets.md`](docs/subscriptions-and-budgets.md).
4. Create a Personal Access Token for the importer and, later, one per MCP server.
5. Import. [`fixtures/`](fixtures/) has a synthetic month and an importer config that exercise the whole account structure, if you want to see it work before feeding it your own statements.

### 1.3 The Data Importer

The importer (`http://<host>:8081`) takes a CSV plus a JSON configuration mapping columns to roles. Three conventions save a lot of grief and are baked into the fixture and the agent procedure:

- The owning statement account is the `account-id` / `account-name` role on **every** row, deposits and transfers included; the counterparty is `opposing-*`. Direction comes from the amount's sign. On transfers this is counter-intuitive: **import one row and look before a batch.**
- Every row gets a **unique, human-legible note** with its source file and row number. The importer's duplicate detection is otherwise happy to skip the second of two legitimate same-day, same-amount charges.
- Every run sets an **import-cycle tag** (`<account>-YYYYMM`). It is how you later tell a statement-derived row from a workflow-posted one, and how the gathering procedure measures how far behind you are.

---

## 2. A chart of accounts that holds up

Firefly's data model is simple — asset accounts, liabilities, expense and revenue payees, categories, tags, budgets, subscriptions — and it is very easy to grow a mess in it. [`docs/taxonomy.md`](docs/taxonomy.md) is the structure a real household has run since early 2026, with every institution replaced by a generic label. The shapes that carry the load:

| Shape | What it is | Why |
|---|---|---|
| **Cards as `ccAsset`** | A credit card is an asset account with a negative balance | Firefly's model; a card payment becomes a transfer, which reconciles |
| **Middle-man account** | A no-branch savings bank sitting between the traditional bank and the broker | Money in flight is always visible somewhere |
| **Marketplace clearing** | One card line for a marketplace order is parked; itemised rows come out of clearing | The card sees one amount; the order has five items in three categories |
| **Gift-card wallets** | Stored value is a `cashWalletAsset`; the card line is the *load*, the spend comes later | Booking the load as an expense double-counts and mis-dates |
| **Broker cash mirrors** | Investment accounts exist in Firefly only as cash-movement mirrors | Holdings and performance live in Ghostfolio; Firefly carries the transfer, not the securities |
| **Liabilities by purpose** | Mortgage, primary HELOC, rental HELOC, portfolio LOC, sales tax collected, income tax payable | Each has different deductibility and a different settlement pattern |
| **Property in the name** | `Utilities – Rental` and `Utilities – Primary Residence`; the same utility company has two payees | A rule can key on the payee id instead of guessing the property from the amount |
| **Two tag axes** | Cost centre (`personal`, `home-office`, `business-travel`, …) and behaviour (`fixed`, `variable`, `subscription`), plus year and import-cycle tags | The accountant filters on the first; budgets and subscriptions rely on the second |

### 2.1 Itemising what the statement shows as one line

Two kinds of spend defeat a statement-driven ledger and deserve their own page: **rideshare trips** (each leg and tip is a separate charge; the business-or-personal decision lives on the receipt email, not the statement) and **marketplace orders** (one charge per shipment, many items across categories). [`docs/itemisation.md`](docs/itemisation.md) sets out both pipelines on the same three principles: the statement is authoritative for the amount, receipts and order exports only *enrich* it, and the unit of classification is the day for rideshare and the order for a marketplace. Each pipeline reports its own health as one number — unmatched rideshare charges, and the balance of the marketplace clearing account, which *is* your un-itemised spend. The reference install found a tenth of a year's spend sitting there before this was built.

---

## 3. Subscriptions and budgets

Two features that installs either skip or set up so that they generate noise. [`docs/subscriptions-and-budgets.md`](docs/subscriptions-and-budgets.md) covers both; the design decisions in one paragraph each:

**A subscription is an expectation**, not a record of spend: *this payee charges between X and Y every period from this anchor date.* Its value is making an **absence** visible — the charge that stopped, doubled, or should have ended with the season. Set a min/max band, an anchor date in the past, an end date for anything seasonal, group them (`Home`, `Rental`, `Consulting`, `Entertainment`, `Financial`, `Health`, `Food`), and accept the auto-rule Firefly offers — then choose its trigger deliberately: **destination id** when the payee is unique to the subscription, **description + amount band in strict mode** when several subscriptions share a payee.

**A budget is an envelope**, one per decision you can actually make about an amount. One transaction, one budget, withdrawals only — a budget is a partition, so take the finer grain. Monthly `reset` envelopes for the steady categories; annual `rollover` envelopes for the lumpy ones (travel, education, maintenance). Contractual, pass-through, capital and rental-P&L spend stays deliberately unbudgeted. Assign by rules keyed on category, and keep one guard rule that *clears* the budget for every non-household category, because rules only ever set a budget and never remove one. Auto-budget limits are created by the cron job — see §1.1.

---

## 4. Connecting an AI assistant (MCP)

[`daften/fireflyiii-mcp`](https://github.com/daften/fireflyiii-mcp) puts ~140 tools in front of the Firefly API — accounts, transactions, categories, budgets, bills, tags, search, summaries — over HTTP. [`compose/firefly-mcp/`](compose/firefly-mcp/) is a ready-to-run stack for it; it joins the Firefly stack's network so it can reach the core by container name. The configuration that matters:

```dotenv
FIREFLY_URL=http://firefly_iii_core:8080     # container name on the shared network
FIREFLY_TOKEN=<personal access token>        # the ONE Firefly user this server represents
MCP_READ_ONLY=true                            # start here; flip only for a user whose data an assistant may change
MCP_PRESET=default
```

Register it in Claude Code with

```bash
claude mcp add --transport http fireflyiii http://<nas-ip>:8490 \
       --header "Authorization: Bearer <firefly personal access token>"
```

The server is one Firefly user; Firefly is single-tenant per user, so run one server per user you want an assistant to see and name each registration for that user. `GET /health` needs no auth and is what the compose healthcheck uses.

What the API will do to an assistant that has not been warned is collected in [`agent/docs/firefly-facts.md`](agent/docs/firefly-facts.md): the two transaction ids (the MCP `id` is the *group*; a journal id fed to an update hits a different record and reports success), liabilities paid by withdrawal and never by transfer, a bulk-update tool that advertises fields the server rejects, and a dozen more. Read it before letting anything write.

---

## 5. Letting an AI assistant keep it current

Reading is the easy half. [`agent/`](agent/) packages two procedures: a **gathering run** that measures how far behind Firefly actually is (from the last *statement-derived* row per account, not `last_activity`, which workflow postings keep current) and emits a tickable checklist of files to download; and an **import procedure** that validates statement continuity, maps deterministically, holds the ambiguous, gives every row a stable identity, and verifies after import by reading back. Nothing is written without an explicit go-ahead. It ships as Claude Code skills and a sub-agent, and as a system prompt for any other MCP-capable assistant. Setup and a worked month-end are in [`agent/README.md`](agent/README.md).

---

## 6. Screenshot tour, sanitized

[`tools/screenshots.mjs`](tools/screenshots.mjs) logs into a Firefly install with Playwright and, **before capturing each page, rewrites the rendered DOM in place**: every institution and personal name from a map you provide becomes its generic label, account and card numbers are masked, every amount is multiplied by a factor so relative sizes survive but no real figure does, and the page text is then re-scanned for every original term. A page where anything survived is reported as UNSAFE and **no file is written**. `DUMP_HTML=1` also saves the sanitized DOM as text for review.

```bash
cp tools/sanitize-map.example.json tools/sanitize-map.json        # fill in YOUR strings on the left (gitignored)
FF_URL=https://firefly.example.lan FF_EMAIL=you@example.com FF_PASSWORD_CMD="pass show firefly" \
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright/index.mjs node tools/screenshots.mjs
```

The captures below come from a **demo user on the reference install, seeded with the synthetic fixture** by [`tools/seed_demo.py`](tools/seed_demo.py) (accounts, categories, budgets with limits, subscriptions in groups, and the fixture's month replicated into the current and previous month). Every figure is invented; the only rewrites the tool had to make were the demo login's email and the LAN hostname.

| | |
|---|---|
| [Dashboard](docs/screenshots/01-dashboard.png) — net worth, per-account activity, budgets, categories, expense and revenue payees | [Budgets](docs/screenshots/06-budgets.png) — 11 monthly `reset` envelopes and 3 annual `rollover` envelopes, with spent and left per day |
| [Asset accounts](docs/screenshots/02-asset-accounts.png) — bank, card, clearing, gift-card wallet, broker mirrors, by role | [Subscriptions](docs/screenshots/07-subscriptions.png) — 17 expectations in 7 groups, with bands, next match and per-group monthly cost |
| [Liabilities](docs/screenshots/03-liabilities.png) — mortgage, two HELOCs, sales tax collected, income tax payable | [Categories](docs/screenshots/08-categories.png) and [Tags](docs/screenshots/09-tags.png) |
| [Expense payees](docs/screenshots/04-expense-accounts.png) and [Revenue payees](docs/screenshots/05-revenue-accounts.png) | [Withdrawals](docs/screenshots/10-withdrawals.png) — both HELOC interest legs, the marketplace clearing itemisation, the gift-card spend | 
| [Transfers](docs/screenshots/11-transfers.png) — card payment, clearing and wallet loads | [Default financial report](docs/screenshots/13-reports.png) for the month — balances, income vs expenses, budgets, categories; and [Rules](docs/screenshots/12-rules.png) |

Seed your own demo user the same way (a second Firefly user, its own Personal Access Token; the script refuses a user that already has transactions):

```bash
FF_URL=https://firefly.example.lan FF_DEMO_PAT=<demo user's token> python tools/seed_demo.py --months 2 --dry-run
FF_URL=https://firefly.example.lan FF_DEMO_PAT=<demo user's token> python tools/seed_demo.py --months 2
```

---

## Support

If this project helps you, sponsorship is appreciated but never required.

<a href="https://www.buymeacoffee.com/ANPCAI" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-blue.png" alt="Buy Me A Coffee" width="180">
</a>

---

## Layout

```
sanitize/                              PDF → pseudonymised text, with a names file; READ ITS README FIRST
compose/firefly/                       Firefly III + MariaDB + Data Importer + cron (+ backup) compose stack
compose/firefly-mcp/                   daften/fireflyiii-mcp compose stack, one per Firefly user
docs/taxonomy.md                       accounts, liabilities, payees, categories, tags — generic labels
docs/subscriptions-and-budgets.md      what the two features are for and how the reference install uses them
docs/itemisation.md                    rideshare trips and marketplace orders: enrich the statement, never replace it
fixtures/                              a synthetic month of transactions + Data Importer config
agent/                                 gathering + import procedures: Claude Code skills/agent, generic system prompt
tools/screenshots.mjs                  Playwright tour that sanitizes the DOM before every capture
tools/seed_demo.py                     seeds a demo Firefly user with the fixture through the REST API
docs/screenshots/                      the tour, captured from the seeded demo user
```

License: MIT for the code in this repository. Firefly III is AGPL-3.0; nothing from it is vendored here.
