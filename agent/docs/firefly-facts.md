# Firefly III through MCP — standing facts

Things about Firefly III 6.6 and its API that an assistant working through an MCP server must know, because each of them has produced a wrong write or a wrong conclusion at least once. They are facts about the software, not about any particular household. Verified against 6.6.6 between 2026-08-11 and 2026-09-03 unless stated.

## Identifiers

- **A transaction has two ids.** `transaction_group_id` is the wrapper; `transaction_journal_id` is the individual split leg. **The MCP `id` field is the group id**, and so are the ids `update_transaction`, `get_transaction` and `delete_transaction` take. Journal ids appear inside `transactions[].transaction_journal_id`. They agree on only a minority of records (in one install, 18 %). Any id list derived from SQL against `transaction_journals` holds journal ids and must be translated through `transaction_journals.transaction_group_id` before feeding a write. **Assuming they are equal is a coin flip that loses four times in five, and the wrong write succeeds silently.**
- Before any write that targets one transaction, `get_transaction` it and confirm description and amount match the intent. A response echoing an unexpected description means the wrong record was addressed — revert immediately.

## Accounts and liabilities

- **Paying a liability is a `withdrawal` whose destination is the liability; a refund out of one is a `deposit` whose source is the liability.** Firefly rejects `type=transfer` with a liability counterparty ("could not find a valid destination account"). Re-pointing a row changes source or destination, never type.
- **The MCP `create_account` cannot create a liability correctly.** It exposes no `liability_type` or `liability_direction`, which Firefly requires. Create liabilities in the UI, then read them back by name. `update_account` with an opening balance on a liability returns a server error; book the opening position as a dated row against a placeholder equity account excluded from net worth instead.
- **Read `current_balance` on a liability, not `debt_amount`.** `debt_amount` sums only withdrawals-in and ignores deposits-out, so it misstates any liability that has had a refund.
- **The account route reports `credit_card_type` and `monthly_payment_date` as `null` even when they are set.** Both live in `account_meta` (`cc_type`, `cc_monthly_payment_date`); the API carries the keys but nulls them. Never conclude a card is unconfigured from the API. `monthlyFull` is the only `cc_type` Firefly ships.
- `get_account_transactions` **silently ignores its `type` filter** (asking for `withdrawal` returned a deposit) but honours `start`/`end`. Filter client-side on `transactions[].type`. The `type` filter on `get_transactions` does work.

## Writes

- **`bulk_update_transactions` cannot set budgets, categories, tags or notes.** Firefly's bulk endpoint accepts `account_id` and nothing else (`config/bulk.php`); the MCP tool advertises fields the server rejects with HTTP 500. Use rules, or per-transaction updates.
- **There are no rule or rule-group MCP tools.** Rules need the REST API. `/api/v1/rule-groups` is hyphenated; `/api/v1/rules` is not.
- **`create_budget` rejects `auto_budget_type: "none"`.** Omit the field instead.
- **Multi-leg split transactions:** the MCP update takes a flat payload and can collapse the split. Edit those in the UI, or leave them.
- **Passing fields you are not changing can overwrite them.** Pass only what changes.

## Rules and budgets

- **Rules only ever *set* a budget; they never clear one.** A transaction recategorised out of a budgeted category keeps its old budget link unless a guard rule clears it. Keep one rule that lists every non-budgeted category and clears the budget.
- **The set-budget action skips anything that is not a withdrawal**, so a deposit sharing a mapped category is safely ignored. No transaction-type trigger is needed on budget rules.
- `artisan firefly-iii:apply-rules` requires both `--token` and `--accounts` and refuses to run without an explicit account list.
- **Auto-budget limits are created by the cron job.** Without something calling `/api/v1/cron/<token>` daily, budgets exist but no limit is ever created and the page stays empty. Verify by checking that `configuration.last_ab_job` advances.

## Subscriptions (bills)

- The API still calls them **bills** (`/api/v1/bills`); the UI calls them subscriptions. `GET /api/v1/bills/{id}/rules` lists the auto-rules attached to one.
- `next_expected_match` is computed from the anchor `date` and `repeat_freq`. A subscription whose anchor is in the future never matches.

## Data importer (FIDI)

- Its `account-id` / `account-name` role is the **owning** side of the row, not the literal source. Direction comes from the amount's sign (or the type column, if you map it). On transfers this is counter-intuitive; **import one row and check before a batch.**
- **Duplicate detection fingerprints survive soft-deletes.** A deleted transaction still blocks an identical re-import. A corrected re-import needs either an in-place update of the original, or a replacement row with a new stable source-derived note. Purging soft-deleted rows is a database operation and out of scope for an assistant.
- The importer appends its configured import tag to every row. Treat a row's *source* tags as a required subset when verifying, and report only unexpected or missing tags.

## Reading the database directly

Permitted as a last resort for questions the API cannot answer (e.g. what is actually stored, versus what the API reports), and read-only. With `MYSQL_RANDOM_ROOT_PASSWORD` there is no root credential; use the application user through a temporary `--defaults-extra-file` that is removed afterwards. The client binary in the MariaDB container is `mariadb`, not `mysql`. **Never filter shell output with a prefix a data row could share** — dropping lines starting with `Enter` to hide the password prompt also drops every row starting with `Entertainment`.

## Operational

- Take a fresh dump before any batch write (`docker exec firefly_iii_backup /backup.sh`); do not rely on the nightly one.
- The summary and balance figures are cached briefly; after a write, re-read a few seconds later.
- Firefly sends no notifications unless a mail or push channel is configured; the bill-reminder preference being on proves nothing.
