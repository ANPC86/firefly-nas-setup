# Subscriptions and budgets in Firefly III

Two features that new installs either skip or set up so that they generate noise. Both are worth doing; both need one design decision made first.

---

## Subscriptions (Firefly calls them *bills* in the API)

A subscription is an **expectation**: *this counterparty will charge me between X and Y every period, starting from this anchor date.* Firefly then does three things with it: it links matching transactions to the subscription (via a rule), it shows which expected charges have and have not arrived this period, and it can warn you before the next one.

The point is not tracking what you spent; a category does that. The point is **seeing an absence.** A charge that stopped, a charge that doubled, a seasonal service that should have ended — each is visible only if something expected it.

### Fields, and how to set them

| Field | Set it to | Why |
|---|---|---|
| **Amount min / max** | A band around the observed charges, e.g. 85–95 for a bill that fluctuates with usage; identical min and max for a fixed price | The band is a *trigger condition* for the auto-rule. Too tight and a price increase silently unlinks it; too loose and an unrelated charge links |
| **Date** | The **first date the charge ever appeared** — the anchor. If it has been running for years, set it in the past | Firefly projects the schedule forward from this date. Weekly → anchor day of week; monthly → anchor day of month |
| **Repeats** | weekly / monthly / quarterly / half-year / yearly | |
| **Skip** | 0 normally; 1 for a two-yearly renewal set as yearly | |
| **End date** | Set it for anything seasonal or a fixed-term bundle | A sports-season stream that ends in spring should not show as "missing" in summer |
| **Extension date** | When a prepaid term ends | Useful for multi-year bundles |
| **Group** | A small set of object groups: `Home`, `Rental`, `Consulting`, `Entertainment`, `Financial`, `Health`, `Food` | The subscriptions page groups by it, which is how you see "what does the rental cost me every month" at a glance |
| **Notes** | What it is, in plain words, and any decision about it ("two-year bundle, effective X/yr, next renewal Sep 2027") | Future you will not remember |

### The auto-rule — accept it, then choose its trigger deliberately

When you save a subscription, Firefly offers to create a matching rule. Accept it, then open the rule and choose **one of two trigger strategies**:

| Strategy | Trigger(s) | Use when |
|---|---|---|
| **A — destination id** | *Destination account id is exactly …* | The payee is unique to this subscription (one payee account per subscription — see the payee naming rule in [taxonomy.md](taxonomy.md)). Cleanest; immune to description changes |
| **B — description + amount** | *Description contains …* **and** *Amount ≥ min* **and** *Amount ≤ max*, **strict mode on** | Several subscriptions share one payee (a marketplace that bills both an annual membership and a monthly channel bundle; an app store that bills three different services). Description isolates; amount guards |
| **A + B** | Both | The same utility serves two properties through two payees, and you want the amount band as a second check |

Keep **strict mode on** (all triggers must match). Strict mode off means *any* trigger is enough, which links every small charge with a matching word.

Order of operations for a new install: **create subscriptions first, accept their rules, then import history.** The rules run on import and link everything in one pass. Creating them afterwards means re-running rules over old transactions, which Firefly can do but it is slower and easier to get wrong.

### What is not a subscription

- A **variable usage charge** with no fixed cadence (cloud API usage, a rideshare). Give it a payee and a tag; do not make it a subscription. It will show "missing" half the months and teach you to ignore the page.
- A **one-time charge** that happened to be a trial. Cancel the trial; do not create the subscription.
- A **transfer** (a savings sweep, a card payment). Subscriptions are withdrawals to expense accounts.

### The reference install's subscriptions, by group

Thirty-one entries. Generic names; the amounts are omitted deliberately.

| Group | Subscriptions | Repeats |
|---|---|---|
| Home | Utility – primary (wide seasonal band), property-tax instalment plan, home insurance, internet, homeowners' association, warehouse-club membership | monthly; membership yearly |
| Rental | Utility – rental, condo fees, property-tax instalment plan, rental insurance | monthly; insurance yearly |
| Consulting | Mobile phone, three cloud/AI subscriptions, a password-manager/VPN bundle (two-yearly), a home-automation cloud, a publishing platform, a network-security subscription, a portfolio tracker | monthly and yearly |
| Entertainment | Two sports streams (seasonal, with end dates), a video platform, a marketplace membership, a media-server add-on, an investing-community app | monthly and yearly |
| Financial | Annual card fee, monthly card fee, credit monitoring | monthly and yearly |
| Health | Benefits premium | monthly |
| Food | Meal kit | weekly |
| (no group) | Telecom – parents | monthly |

The mix is the lesson: one group is *what the property costs to hold*, one is *what the business costs to run*, one is *what I chose to pay for*. The groups make the monthly total per group a one-glance figure.

---

## Budgets

A budget in Firefly is an **envelope** with a limit per period. One transaction can belong to **one** budget, and **only withdrawals** count. A budget is therefore a *partition* of your spending, not an overlay on it — you can aggregate envelopes upward later; you can never split a coarse budget back into fine ones. Take the finer grain.

### The test for whether something deserves a budget

*Is there a decision about the amount that you could actually make?* Groceries: yes. Dining out: yes. Mortgage principal: no — it is contractual; put it in subscriptions. Tax remittances: no — pass-through. Rental property costs: no — that is an investment P&L with its own discipline, not household consumption. Investment contributions: no — balance sheet.

In the reference install that test leaves **14 budgets** covering roughly a sixth of gross outflow. Everything else is contractual, pass-through, capital, or a separate P&L, and is deliberately unbudgeted.

### Period: monthly for the steady, annual for the lumpy

Setting an annual-shaped cost as a monthly budget produces meaningless red and green every month. Firefly's **auto-budget** feature sets the period per budget:

| Auto-budget type | Behaviour | Use for |
|---|---|---|
| `reset` | A fresh limit every period; unspent does not carry | Steady monthly envelopes — groceries, dining, housing operating, health, subscriptions, household goods, entertainment, transportation, fees, family support, the catch-all |
| `rollover` | Unspent carries into the next period | Annual envelopes for lumpy spend — personal travel, education, home maintenance. The limit measures the thing you control, which is the yearly total |
| `adjusted` | Rollover, but the *limit* is also recomputed | Rarely what you want; skip it until you have a reason |

Auto-budget limits are created **by the cron job**. If nothing calls Firefly's cron endpoint, budgets exist but no limit ever appears and the budget page stays empty. The compose stack in this repository includes the cron caller; if you build your own, check that `configuration.last_ab_job` advances.

### Mapping categories to budgets with rules

A budget is assigned per transaction, and Firefly's bulk-update endpoint cannot set it (it accepts `account_id` and nothing else, whatever the UI suggests). So the mapping is done by **rules**, one rule group, one rule per budget:

- Trigger: *Category is …* (one trigger per mapped category, **strict mode off** so any of them fires).
- Action: *Set budget to …*.
- No transaction-type trigger is needed: the set-budget action already skips anything that is not a withdrawal.

One rule that is easy to forget, and the reason it exists: **rules only ever set a budget; they never clear one.** A transaction recategorised *out* of a household category keeps its old budget unless something removes it. Add a final guard rule — trigger: category is any non-household category; action: *clear budget* — or you will find rental and business rows quietly inflating household envelopes.

### The reference install's budgets

| Budget | Period | Categories it partitions |
|---|---|---|
| Groceries | monthly, reset | Groceries & Food |
| Dining Out | monthly, reset | Dining Out |
| Housing – Operating | monthly, reset | Utilities, property tax, insurance — primary residence |
| Health & Personal Care | monthly, reset | Health Care – Personal, Personal Care, Insurance – Personal |
| Subscriptions & Digital | monthly, reset | Software & Subscriptions |
| Household Goods & Clothing | monthly, reset | Household Goods, Clothing, Electronics – Personal |
| Entertainment & Recreation | monthly, reset | Entertainment |
| Transportation | monthly, reset | Transportation |
| Family Support & Gifts | monthly, reset | Family Support, Charitable Donations |
| Bank & Card Fees | monthly, reset | Bank Fees |
| Unallocated | monthly, reset, **limit set below run-rate** | Personal Misc |
| Travel – Personal | yearly, rollover | Personal Travel |
| Education & Development | yearly, rollover | Education |
| Home Maintenance & Repair | yearly, rollover, **limit set above run-rate** | Maintenance – Primary Residence |

Two limits are set against the evidence on purpose, and the reason is worth copying. *Unallocated* is set **below** what lands there so that the red bar is a monthly prompt to decompose the catch-all; two new categories came out of exactly that pressure. *Home Maintenance* is set **above** the observed run-rate because a house under-provisions for maintenance until the year it does not, and the rollover accumulates the provision.

### Sizing a limit

Take 18–24 months of history per mapped category, look at the distribution, and set the limit near the **70th percentile of monthly totals** for steady categories — not the mean, which a single bad month drags, and not the median, which makes half your months red. For annual envelopes take the annualised total. Then decide deliberately where to depart from the evidence, and write the reason in the budget's notes.

### What budgets are not for

Do not encode a classification (essential vs discretionary, needs vs wants, retirement-relevant vs not) into budgets. One transaction, one budget: the moment a budget means two things you lose one of them. Keep classifications in a mapping table outside Firefly keyed off the category; keep budgets as envelopes.
