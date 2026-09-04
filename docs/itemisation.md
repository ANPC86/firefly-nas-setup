# Itemising what the statement shows as one line

Two kinds of spend defeat a statement-driven ledger: **rideshare trips** and **marketplace orders**. In both, the card statement is correct about the money and useless about the meaning. A rideshare line says *Rideshare 23.80*; whether that was a client visit or a cinema trip is on the receipt email. A marketplace line says *Marketplace 213.55*; that it was a USB-C dock, a kitchen scale and a paperback — three categories, one of them business — is in the order export. The reference install had **a tenth of a year's spend** sitting un-itemised in the marketplace line before this was built.

Three principles, then the two pipelines.

1. **The statement is authoritative for the amount.** It is the settled charge, it never misses a transaction, and it is already imported. Receipts and order exports are *enrichment* — identity, purpose, item — never the number of record.
2. **Enrich, never replace.** An unenriched charge stays visible as a count. That count is the tripwire: when the receipt parser breaks or the order export was not run, the number rises instead of trips silently disappearing.
3. **Classify at the right unit.** For rideshare it is the **day** (legs and tips are separate charges of one outing). For a marketplace it is the **order** (one charge, many items; sometimes many charges, one order).

---

## Rideshare trips

### What the statement gives you, and what it does not

Each leg is a separate charge. A tip is another charge, same day, sometimes minutes later. An adjustment is a third. So one outing to a client and back is typically four to five card lines, none of which says where you went.

### Where the meaning is

The receipt email: timestamp, fare, pickup and drop-off. That is the only free source that carries the fare. The official alternatives were evaluated and do not work for a personal ledger:

| Source | Carries the fare | Covers personal trips | Verdict |
|---|---|---|---|
| Receipt email | Yes | Yes | **Use it** |
| Riders API `GET /history` | No | Yes | No money in the payload |
| Business receipts API / SFTP export | Yes | No — business-profile trips only, enterprise agreement | Partial at best |
| Privacy data download | No — pricing excluded explicitly | Yes | Good for route and duration, never for amounts |

### The pipeline

1. **Parse receipts into a trip log.** A mail-rule or script (Apps Script, n8n, a local IMAP parser — anything that never hands your mail credentials to a third party) turns each receipt into a row: date, amount, pickup, drop-off, a link back to the email, and an empty *purpose* column. Trip metadata is personal data; the log lives in `.local/`.
2. **Classify by day.** Group the log by date. For each day, decide business or personal from the *outbound* destination and write the reason in the purpose column (`Business – client site – networking`, `Personal – cinema`). Keep a short standing rule list ("a weekday outbound to the client's district is business unless noted"); days no rule covers are flagged, not defaulted.
3. **Match to the statement, not the other way round.** Every rideshare charge in Firefly for the period gets the classification of its day. Tips inherit the day's classification. A charge with no parsed trip is left in place and counted.
4. **Book.** The payee stays *Rideshare*. Business days: category *Travel – Business*, tags `t4a, business-travel` (100 % deductible transport; keep the receipt link in notes as documentation). Personal days: category *Transportation* (or *Personal Misc* for an outing that is not commuting), tags `personal, variable`. **The category carries deductibility; the tag does not.**
5. **Tripwire.** Per period: `charges on statement − trips parsed`. Non-zero means the parser missed something or a template changed. Look at it monthly.

### Two boundary effects to expect

- A trip on the last day of a card cycle posts to the **next** statement. It is not missing; it is pending. Record the classification decision now (in the pending-entries register) so that when the charge lands in the next cycle it is booked personal rather than defaulted to the standing rule.
- A day with a single inbound leg and no outbound is **unclassifiable** from the log. Leave it at the existing classification and say so; do not invent a purpose.

---

## Marketplace orders

### The problem

The card sees one line per charge. The marketplace charges **per shipment**, so one order can be one, two or three lines, and a return is a later credit that references none of them by name. Meanwhile the order has five items in three categories, one of which is a business expense.

### The clearing account

Book the card line **into a clearing account**, not to an expense:

| Movement | Type | From | To | Category |
|---|---|---|---|---|
| Card charge for the order | withdrawal | Credit card | **Marketplace Clearing** (`cashWalletAsset`) | Balance Sheet Transfer |
| Each item | withdrawal | Marketplace Clearing | Marketplace (expense payee) | the item's category |
| Refund credited to the card | deposit | Marketplace Clearing | Credit card | Balance Sheet Transfer |
| Gift card applied at checkout | transfer | Gift Card Balance – Marketplace | Marketplace Clearing | Balance Sheet Transfer |

The clearing account's balance is then **un-itemised spend, as a number**. Zero means every order has been broken out. Growing means the backlog is growing. Report it monthly; it is the single most useful figure this pattern produces.

### The source

The marketplace's own order export ("Your Orders", request-your-data, or the order-history report, depending on the vendor): one CSV row per item, with order id, order date, item name, quantity, unit price, total charged, and payment method. Export it per date range, into `.local/`, after the card statement for the same period is imported.

### The pipeline

1. **Import the card statement first.** Every marketplace line goes to *Marketplace Clearing*, tagged with the import cycle. This is mechanical and happens in the normal cycle.
2. **Export orders for the same window** and match each order's item total to the card lines by order id and date. A multi-shipment order matches the *sum* of its lines. An order paid partly by gift card matches the card line plus the wallet transfer.
3. **Itemise.** One withdrawal per item (or per group of like items) from clearing to the *Marketplace* payee, category from the item, tags from the purpose. Note: `order=<id> item=<n>` — the stable identity that makes a re-run idempotent and lets you trace any row back.
4. **Reconcile.** Clearing balance after itemisation equals the un-itemised remainder, which should be the orders you have consciously deferred and nothing else.

### Rules that hold

- **A gift card bought on the card is a load, not a spend.** It is a transfer card → wallet; the spend is booked from the wallet when the gift card is used. Booking the load as an expense double-counts and puts the spend in the wrong month.
- **Deferred is fine; guessed is not.** If an order's items are not yet known (a pre-order, a split shipment not yet charged), leave it in clearing and write it in the pending-entries register. Do not invent the itemisation to get to zero.
- **Business items get the review tag.** An item that is a business expense carries `t4a, home-office, accountant-review` in addition to its category. The order export is the receipt; keep the export.
- **Refunds go back through clearing.** A refund is not income and not a negative expense; it reverses a specific item. Book the credit into clearing and, if the item was already itemised, a deposit from the *Marketplace* payee back into clearing against the same `order=` note.

---

## Why this is worth the effort

Without it, two of the largest discretionary lines in a household — getting around and buying things online — are opaque: a rideshare total you cannot split between deductible and personal, and a marketplace total that hides a business laptop next to a bag of coffee. With it, both become ordinary categorised spend with a receipt behind every row, and each pipeline reports its own health as a single number: unmatched charges for rideshare, clearing balance for the marketplace.
