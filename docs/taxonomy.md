# A working chart of accounts for Firefly III

This is the account, payee, category, tag, budget and subscription structure that a real household has been running in Firefly III since early 2026 — one earner with contract income, a partner sharing household costs, a primary residence with a mortgage and a line of credit, a rental condo with its own line of credit, four credit cards, an online broker, and a self-hosted stack that an AI assistant reads through MCP.

Every name below is a **generic label** for what the account *is*, not who it is with. *Traditional Bank* is a big-five retail bank; *Online Bank* is a no-branch savings bank; *Online Broker* is a discount brokerage with a cash account attached. Use the labels as they are, or substitute your own institutions — the structure is what transfers. Amounts appear nowhere in this file.

The Canadian tax-form tags (`t776`, `t4a`, `t1`, `GST`) are named for the schedules they feed. Rename them for your jurisdiction; keep the idea that a tag marks *which return a row belongs to*.

---

## 1. Asset accounts

Firefly's *account role* is what drives its behaviour, so it is listed first.

| Generic name | Role | What it is | Why it is its own account |
|---|---|---|---|
| Traditional Bank – Joint Chequing | `sharedAsset` | Operating account for the rental property and shared household costs | Rental income and rental bills flow through here; keeping them off the personal account makes the rental P&L reconcilable |
| Traditional Bank – Savings | `savingAsset` | Main personal account; contract income lands here | Everything personal starts from this account |
| Traditional Bank – USD Chequing | `savingAsset`, USD | Foreign-currency cash | Firefly is multi-currency per account; do not mix currencies in one |
| Online Bank – High-Interest Savings | `savingAsset` | **The middle-man.** Receives inter-bank transfers from the Traditional Bank, forwards to the Online Broker | Every hop is visible; a transfer that never arrived is a row that never appeared |
| Online Bank – Chequing | `defaultAsset` | The account the credit cards are paid from | One card-payment source, so card payments reconcile against one statement |
| Online Broker – Cash | `cashWalletAsset` | The broker's chequing-like cash account; pays the odd bill, funds the prepaid card | Its statement is a real statement; treat it like a bank |
| Online Broker – Savings | `savingAsset` | Interest-bearing cash at the broker | Interest income needs a distinct source |
| Online Broker – Non-Registered (CAD) / (USD) | `savingAsset`, one per currency | **Cash-movement mirror** of the investment account | Holdings and performance live in Ghostfolio; this account only carries the cash in and out so transfers have a counterparty |
| Online Broker – TFSA / RRSP | `savingAsset` | Same mirror idea for registered wrappers (ISA, 401k, whatever yours are called) | Contributions and withdrawals appear on the broker's cash statement as bare "transfer in/out"; the mirror gives them a destination |
| Traditional Bank Visa | `ccAsset`, `monthlyFull` | Travel-points card | A card is an asset account with a negative balance, not a liability — that is Firefly's model and it makes the payment a transfer |
| Charge Card | `ccAsset` | Monthly-fee premium card | Its statement cycle is not calendar-aligned; see `firefly-updater.md` |
| Retailer Mastercard | `ccAsset` | Store-branded card | Most of its spend is one marketplace, which is why the clearing account below exists |
| Online Broker Prepaid Card | `ccAsset` | Pay-in-full card funded from the broker's cash | Cashback is **income** from a revenue account, never a card→cash transfer |
| Gift Card Balance – *Retailer* (one per retailer) | `cashWalletAsset` | Stored value bought on a card, spent later | **Load** is a transfer card→wallet; **spend** is a withdrawal wallet→expense. Never book the statement's gift-card line as an expense: that is the load, not the spend |
| Marketplace Clearing | `cashWalletAsset` | Where a single card line for a marketplace order waits until the order is itemised | The card shows one amount; the order has five items in three categories. The card line is a transfer into clearing; the itemised rows are withdrawals out of it. A clearing balance that keeps growing is unitemised spend you can see |
| Partner Shared Pool | `sharedAsset` | Represents the partner's contribution to shared costs | Their share of the mortgage and household bills is a deposit here, not income to you |
| Opening Balance Equity | `defaultAsset`, **excluded from net worth** | Placeholder counterparty for opening balances the API cannot set on a liability | Mirrors Firefly's own hidden initial-balance mechanism. Not a real account; nothing ordinary is booked against it |

Two of these do work that is easy to underrate: the **middle-man** savings account and the **clearing** account. Both exist so that money is never in an unexplained state. If a transfer is in flight, it is sitting in one of them, visibly. The clearing account, the gift-card wallets and the rideshare payee are the anchors of the two itemisation pipelines in [itemisation.md](itemisation.md).

## 2. Liabilities

Firefly needs `liability_type` and `liability_direction` at creation, and the MCP `create_account` tool cannot supply them — create liabilities in the UI, then read them back by name.

| Generic name | Type | Direction | Notes |
|---|---|---|---|
| Primary Residence Mortgage | `mortgage` | debit | Interest rate and period set on the account; the payment is a **withdrawal** from the bank *into* the mortgage. The interest split is not tracked here; the lender's amortisation schedule is the source for that |
| Primary Residence HELOC | `loan` | debit | Draws are deposits *from* the HELOC to the bank; payments are withdrawals *into* it; interest is a withdrawal *from* the HELOC to an interest expense account |
| Rental Property HELOC | `loan` | debit | Same shape, separate account, because its interest is deductible against the rental and the other one's is not |
| Online Broker Portfolio Line of Credit | `loan` | debit | Drawn to and repaid from the broker's cash account; interest is a withdrawal from the broker's cash to a dedicated interest payee |
| Sales Tax Collected | `debt` | debit | GST/HST/VAT collected on invoices and owed to the tax authority. Each collection is a withdrawal *from* this liability to a "tax collected" expense account, so the balance moves negative = owed; a remittance is a withdrawal from the bank *into* it; the balance is collected − remitted |
| Income Tax Payable | `debt` | debit | Instalments and balance payments are withdrawals from the bank *into* it (balance goes positive = prepaid); the annual assessment is a withdrawal *from* it to the tax authority's expense account (negative = owed); refunds are deposits *out* of it. Every row also carries a `Tax YYYY` tag for the tax year, distinct from the calendar-year tag, so settled years net to zero under their tag |

Two rules that come from Firefly's model, not from preference:

- **Paying a liability is a `withdrawal` whose destination is the liability; a refund out of one is a `deposit` whose source is the liability.** Firefly rejects `transfer` with a liability counterparty. Re-pointing a row therefore changes its source or destination, never its type.
- **Read `current_balance` on a liability, not `debt_amount`.** The API's `debt_amount` sums only withdrawals-in and misstates any liability that has had a refund.

## 3. Payees — expense and revenue accounts

Firefly creates these on the fly from a transaction's counterparty name, which is how installs end up with 400 near-duplicate payees. The rule here: **one payee per counterparty that will recur, named for what it is, with the property or purpose in the name where the same institution serves two purposes.**

### Revenue accounts (money in)

| Generic payee | Feeds category | Note |
|---|---|---|
| Contract Client | Consulting Income | One per client |
| Tenant – Rental | Rental Income | |
| Interest – Online Bank / Interest – Traditional Bank / Interest – Online Broker | Interest Income | One per institution; the interest slip is per institution |
| Card Cashback | Rewards Income | Cashback is income, never a card→cash transfer |
| Insurer – Claim Payout | (none; or Adjusted Cost Base for capital events) | Distinct from the same insurer's *expense* payee |
| Benefits Insurer – Claim Reimbursement | (none) | Deposit back to the account that paid the dentist |
| Partner – Shared Expenses | Shared Expenses | |
| Family Reimbursement | Family Reimbursement | Money flowing **in**; see *Family Support* for money out |

### Expense accounts (money out)

| Generic payee | Typical category | Note |
|---|---|---|
| Utility – Primary Residence / Utility – Rental | Utilities – Primary Residence / – Rental | **Same utility company, two payees.** The property is in the payee, so a rule can key on destination id instead of guessing from the amount |
| Telecom – Mobile | Business Phone / Telecom | |
| Telecom – Parents | Family Support | A bill you pay for someone else is support, not a household utility |
| Municipality – Property Tax | Property Tax – Primary Residence / – Rental | Split by the property, not the payee; the municipality is the same |
| Municipality – Transit | Transportation | A small fixed-band amount identifies it |
| Condo Corporation | Condo Fees | Rental |
| Homeowners' Association | Utilities – Primary Residence | With the *Primary Residence* tag |
| Insurer – Home / Insurer – Rental / Benefits Insurer | Insurance – Primary Residence / – Rental / – Personal | |
| Tax Authority – Income Tax / Tax Authority – Sales Tax Collected | Tax Payments / GST Collected | Both pass-throughs, both excluded from spend analysis by category |
| Accountant | Professional Fees | |
| Traditional Bank – Fees | Bank Fees | Monthly fees, overdraft, and the annual card fee (a description rule isolates the latter) |
| Traditional Bank – HELOC Interest / Online Broker – LOC Interest | Loan Interest – *property or facility* | Interest deducted directly from the facility has the facility as *source* |
| Grocer, Warehouse Club, Meal Kit, Hardware Store, Rideshare, Coffee Chain | Groceries & Food, Household Goods, Transportation, Dining Out | One per merchant that recurs |
| Marketplace | varies per itemised row | Destination for itemised rows *out of* Marketplace Clearing |
| Streaming – *Service*, Cloud – *Service*, AI – *Service* | Entertainment / Software & Subscriptions | One per subscription so the subscription's auto-rule can key on destination id |
| Personal Misc Expenses | Personal Misc | The catch-all for one-off vendors. A budget deliberately set *below* its run-rate keeps pressure on to decompose it |
| Business Expense – Dining Out / Business Expense – Misc | Business Meals & Entertainment / Business Misc | Catch-alls for business spend with no dedicated payee. Receipt required |

## 4. Categories

A category answers *what was this for* and is the axis reports and budgets run on. The install uses one flat list; the grouping below is for reading, not a Firefly feature.

| Group | Categories | Tax relevance |
|---|---|---|
| **Income** | Consulting Income, Rental Income, Interest Income, Rewards Income, Family Reimbursement, Shared Expenses | Self-employment schedule, rental schedule, interest slip; the last three non-taxable |
| **Household, controllable** | Groceries & Food, Dining Out, Entertainment, Clothing, Household Goods, Electronics – Personal, Personal Care, Health Care – Personal, Insurance – Personal, Transportation, Personal Travel, Education, Charitable Donations, Family Support, Personal Misc | Personal; a few (tuition, medical, donations) carry the personal-return tag |
| **Housing – primary residence** | Utilities –, Property Tax –, Insurance –, Maintenance – Primary Residence; Mortgage – Primary Residence | Not deductible, but property tax and insurance are **inputs to a home-office percentage** and carry `home-office` |
| **Rental property** | Rental Income, Utilities –, Property Tax –, Insurance –, Maintenance – Rental, Condo Fees, Rental Equipment, Rental Misc Expenses, Loan Interest – Rental, Adjusted Cost Base | Rental schedule (`t776`). *Adjusted Cost Base* is neither income nor expense: it holds capital events (insurance proceeds, capital repairs) that change the property's cost base and crystallise only on sale |
| **Business** | Business Meals & Entertainment, Travel – Business, Business Phone / Telecom, Business Misc, Office Misc, IT Equipment & Hardware, Software & Subscriptions, Professional Fees | Self-employment schedule (`t4a`). Meals are 50 % deductible, transportation 100 % — **the category carries the deductibility, the tag does not** |
| **Debt service** | Loan Interest – Primary Residence, Loan Interest – Portfolio LOC, Bank Fees | Deductibility depends on use of funds; rows carry `accountant-review` until settled |
| **Balance sheet, no P&L** | Balance Sheet Transfer, CC Payment, Investment, Personal Transfer | Any movement between accounts you own or owe. Categorising these *explicitly* is what makes Firefly's "no category" view a real to-do list instead of noise |
| **Tax pass-through** | Tax Payments, GST Collected | Remittances and collections; excluded from every spend baseline by category |

Naming rules that held up:

- **Property in the name** when the same kind of cost exists for two properties: `Utilities – Rental` and `Utilities – Primary Residence`, never a bare `Utilities`.
- **Business vs personal is a category split**, not a tag: `Dining Out` vs `Business Meals & Entertainment`, `Personal Travel` vs `Travel – Business`. Reports filter by category; tags stack on top.
- **Money in and money out of the same relationship get different categories**: `Family Reimbursement` (in) vs `Family Support` (out).
- A **catch-all is fine as long as it has a budget under its run-rate**. `Personal Misc` at a limit below what actually lands there forces the monthly decomposition that produced `Household Goods` and `Family Support`.

## 5. Tags

Tags are the second axis. They are cheap, they stack, and they are what an accountant filters on. Five families:

| Family | Tags | Rule |
|---|---|---|
| **Calendar year** | `2025`, `2026`, … | Every transaction. It is the cheapest year filter Firefly has |
| **Tax year** | `Tax 2025`, `Tax 2026` | Only on income-tax rows; distinct from the calendar year because instalments for year N are paid in N+1 |
| **Import cycle** | `<account>-YYYYMM`, e.g. `charge-card-202608`, `visa-202608`, `broker-cash-202608` | Set by the importer on every row of a cycle. This is how you later answer "which statement did this come from" and how you tell a statement-derived row from a workflow-posted one |
| **Cost centre** | `personal`, `home-office`, `business-travel`, `rental-maintenance`, `shared-household` | Every card transaction gets exactly one. `home-office` + `t4a` is the self-employment filter; `t776` + `Rental` is the rental filter |
| **Behaviour** | `fixed`, `variable`, `subscription` | `fixed` = same or predictable amount each period; `variable` = fluctuates; `subscription` stacks on `fixed` for recurring digital services |
| **Return** | `t4a`, `t776`, `t1`, `GST` | Which schedule the row feeds |
| **Review** | `review`, `accountant-review` | `review` is your own queue; `accountant-review` is anything mixed-use or ambiguous, mandatory on any percentage split |
| **Debt** | `heloc`, `heloc-draw`, `heloc-payment` | Slices for the debt facilities |
| **Stacking** | `smart-home`, `ACB`, `insurance-claim`, `reimbursed` | Never alone; always on top of a cost-centre tag |

Two of these do most of the work in practice. The **import-cycle tag** is what lets the gathering skill measure how far behind Firefly actually is, because `last_activity` on an account lies whenever a workflow keeps posting rows. The **cost-centre tag** is the one your accountant asks for.

## 6. Budgets and subscriptions

Covered in their own file: [subscriptions-and-budgets.md](subscriptions-and-budgets.md). The short version — a budget is a monthly or annual *envelope* for a decision you can actually make about the amount; a subscription (Firefly's *bill*) is an *expectation* that a specific charge will recur in a band, so its absence is visible.

## 7. What Firefly does and does not hold

| Held in Firefly | Held elsewhere |
|---|---|
| Every cash movement, including into and out of investment accounts | Holdings, cost basis, performance — Ghostfolio |
| Liabilities at current balance | Mortgage amortisation — the lender's schedule |
| Categories, tags, budgets, subscriptions | Retirement-planning classification of categories — a versioned mapping table, not a Firefly field |
| Statement-derived and workflow-posted transactions, distinguishable by tag | The statements themselves — a local, gitignored folder, sanitized before any assistant reads them |

Firefly is the transactions-and-expenses ledger. It is not the portfolio tracker and not the planning model, and the account structure above is what keeps the boundary clean: the broker's accounts exist in Firefly only as cash mirrors.
