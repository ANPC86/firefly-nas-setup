# Sample import — one month of a fictional household

`sample-transactions.csv` is a synthetic month that exercises the account structure in [`docs/taxonomy.md`](../docs/taxonomy.md): a bank account, a credit card, a HELOC with both interest legs, a mortgage payment, a marketplace clearing account, a gift-card wallet, rental income and expenses, card cashback booked as income, and sales tax collected on an invoice. Every row is invented; names are the generic labels from the taxonomy.

`fidi-config.json` is a Firefly III Data Importer configuration that maps the CSV's columns to importer roles. It follows the conventions the import procedure in [`agent/docs/firefly-updater.md`](../agent/docs/firefly-updater.md) relies on:

- The **owning** account of every row is mapped to the `account-name` role, the counterparty to `opposing-name`. These are importer anchor roles, not literal source/destination columns; the sign of the amount carries the direction.
- Amounts are **signed**: negative leaves the owning account, positive arrives. The importer's type detection is left to the amount, so the `type` column is only informative and is ignored (`_ignore`).
- Every row has a **unique, human-legible note** carrying its source reference (`source=sample.csv#row-N`). This is what stops the importer's duplicate detection from skipping a legitimate same-day, same-amount pair.
- Tags include the calendar year and an **import-cycle tag** (`sample-202608`), so every row can be traced to the file it came from.

## Before you import

Create the asset and liability accounts first, in the Firefly UI, with these exact names — the importer resolves owning accounts by name and will otherwise dump every row into its default account:

| Name | Type | Role / liability type |
|---|---|---|
| Traditional Bank – Savings | Asset | savings |
| Traditional Bank – Joint Chequing | Asset | shared |
| Traditional Bank Visa | Asset | credit card, monthly full payment |
| Marketplace Clearing | Asset | cash wallet |
| Gift Card Balance – Coffee Chain | Asset | cash wallet |
| Primary Residence Mortgage | Liability | mortgage, debit |
| Rental Property HELOC | Liability | loan, debit |
| Sales Tax Collected | Liability | debt, debit |

Expense and revenue payees are created by the importer from the `opposing-name` column. Categories must exist by exact name or the importer leaves the row uncategorised; create the ones this file uses from the taxonomy list, or let the importer's mapping step create them.

## Import

1. Open the Data Importer (`http://<host>:8081`), choose **Import from file**, upload `sample-transactions.csv` and `fidi-config.json`.
2. On the roles screen, confirm the roles match the config. On the mapping screen, map each account name to the account you created.
3. **Import one row first** if this is your first time with signed amounts and the owning-account anchor: direction on transfers is the classic place the importer surprises people. Check the result in Firefly, then run the rest.
4. Afterwards, read back a sample through the API or MCP and compare type, source, destination, amount and note against the CSV. The importer's completion screen is not verification.

Status: the CSV and config are written to the importer's documented v3 format and the conventions above, and the same conventions run monthly on the reference install. **This specific fixture has not been round-tripped through a clean Firefly instance** — if you do so and find a mapping the importer disagrees with, open an issue with the importer's log line.
