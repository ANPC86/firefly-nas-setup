"""Seed a Firefly III user with the synthetic fixture, through the REST API.

Creates, for ONE Firefly user identified by a Personal Access Token:
  - the asset and liability accounts the fixture needs (see fixtures/README.md),
  - every category the fixture uses, with notes,
  - the reference install's budgets (monthly reset / yearly rollover) with a limit for the current period,
  - a set of generic subscriptions (bills) in object groups,
  - the fixture's transactions, replicated into the current month and N-1 prior months so charts and
    budgets have something to show.

Everything it writes is synthetic. It is meant for a DEMO user on your own instance — never run it
against the account that holds your real books; it creates ~60 objects and refuses to run if the
user already has any transactions unless --force is given.

    FF_URL=https://firefly.example.lan FF_DEMO_PAT=<token> python tools/seed_demo.py --months 2
    python tools/seed_demo.py --env .local/firefly-demo.env --months 2 --dry-run

Verified against Firefly III 6.6.6.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "sample-transactions.csv"

# ---------------------------------------------------------------------------
# What the fixture needs to exist first. Names must match the CSV exactly.
# ---------------------------------------------------------------------------

ASSETS = [
    # name, role, extra
    ("Traditional Bank – Savings", "savingAsset", {"opening_balance": "4200.00"}),
    ("Traditional Bank – Joint Chequing", "sharedAsset", {"opening_balance": "1650.00"}),
    ("Traditional Bank Visa", "ccAsset", {"credit_card_type": "monthlyFull", "monthly_payment_date": "2026-01-25"}),
    ("Marketplace Clearing", "cashWalletAsset", {}),
    ("Gift Card Balance – Coffee Chain", "cashWalletAsset", {}),
    ("Online Bank – High-Interest Savings", "savingAsset", {"opening_balance": "12000.00"}),
    ("Online Broker – Cash", "cashWalletAsset", {"opening_balance": "900.00"}),
    ("Online Broker – TFSA", "savingAsset", {}),
]

LIABILITIES = [
    # name, liability_type, interest, period, opening balance (negative = owed)
    ("Primary Residence Mortgage", "mortgage", "4.99", "monthly", "-284200.00"),
    ("Primary Residence HELOC", "loan", "4.95", "monthly", "-18000.00"),
    ("Rental Property HELOC", "loan", "4.95", "monthly", "-80000.00"),
    ("Sales Tax Collected", "debt", "0", "daily", None),
    ("Income Tax Payable", "debt", "0", "daily", None),
]

CATEGORY_NOTES = {
    "Family Support": "Support provided to parents and family. Distinct from Family Reimbursement, which is money flowing IN.",
    "Household Goods": "Durable household items that are not Clothing or Electronics – Personal. Maps to the Household Goods & Clothing budget.",
    "Balance Sheet Transfer": "Any movement between accounts you own or owe. Never for interest (Loan Interest) or card payments (CC Payment).",
    "GST Collected": "Sales tax collected on invoices; a pass-through, excluded from spend analysis.",
    "Rewards Income": "Card cashback and rewards received as income.",
}

BUDGETS = [
    # name, auto type, period, amount
    ("Groceries", "reset", "monthly", "1200"),
    ("Dining Out", "reset", "monthly", "550"),
    ("Housing - Operating", "reset", "monthly", "1050"),
    ("Health & Personal Care", "reset", "monthly", "300"),
    ("Subscriptions & Digital", "reset", "monthly", "200"),
    ("Household Goods & Clothing", "reset", "monthly", "150"),
    ("Entertainment & Recreation", "reset", "monthly", "100"),
    ("Transportation", "reset", "monthly", "100"),
    ("Family Support & Gifts", "reset", "monthly", "100"),
    ("Bank & Card Fees", "reset", "monthly", "30"),
    ("Unallocated", "reset", "monthly", "350"),
    ("Travel - Personal", "rollover", "yearly", "12000"),
    ("Education & Development", "rollover", "yearly", "6000"),
    ("Home Maintenance & Repair", "rollover", "yearly", "6000"),
]

# category -> budget, applied on the transactions we post (rules would do this on a real install)
CATEGORY_BUDGET = {
    "Groceries & Food": "Groceries",
    "Dining Out": "Dining Out",
    "Utilities - Primary Residence": "Housing - Operating",
    "Property Tax - Primary Residence": "Housing - Operating",
    "Insurance - Primary Residence": "Housing - Operating",
    "Health Care - Personal": "Health & Personal Care",
    "Personal Care": "Health & Personal Care",
    "Software & Subscriptions": "Subscriptions & Digital",
    "Household Goods": "Household Goods & Clothing",
    "Clothing": "Household Goods & Clothing",
    "Entertainment": "Entertainment & Recreation",
    "Transportation": "Transportation",
    "Family Support": "Family Support & Gifts",
    "Bank Fees": "Bank & Card Fees",
    "Personal Misc": "Unallocated",
    "Personal Travel": "Travel - Personal",
    "Education": "Education & Development",
    "Maintenance - Primary Residence": "Home Maintenance & Repair",
}

BILLS = [
    # name, min, max, repeat, group, notes
    ("Utility – Primary Residence", "50.00", "460.00", "monthly", "Home", "Seasonal band"),
    ("Property Tax Instalment – Primary", "385.00", "900.00", "monthly", "Home", ""),
    ("Home Insurance", "150.00", "500.00", "monthly", "Home", ""),
    ("Internet", "85.00", "95.00", "monthly", "Home", ""),
    ("Utility – Rental", "1.00", "200.00", "monthly", "Rental", ""),
    ("Condo Fees", "499.00", "650.00", "monthly", "Rental", ""),
    ("Property Tax Instalment – Rental", "200.00", "250.00", "monthly", "Rental", "Unit + parking"),
    ("Mobile Phone", "60.00", "100.00", "monthly", "Consulting", ""),
    ("AI Assistant – Cloud", "26.00", "29.00", "monthly", "Consulting", ""),
    ("Password Manager / VPN", "1.00", "300.00", "yearly", "Consulting", "Two-year bundle"),
    ("Sports Stream (season)", "35.00", "40.00", "monthly", "Entertainment", "Set an end date"),
    ("Video Platform", "8.00", "14.00", "monthly", "Entertainment", ""),
    ("Marketplace Membership", "100.00", "110.00", "yearly", "Entertainment", ""),
    ("Card Annual Fee", "120.00", "200.00", "yearly", "Financial", ""),
    ("Credit Monitoring", "13.64", "13.64", "monthly", "Financial", ""),
    ("Benefits Premium", "60.00", "65.00", "monthly", "Health", ""),
    ("Meal Kit", "76.93", "88.93", "weekly", "Food", ""),
]


# ---------------------------------------------------------------------------
# Tiny API client
# ---------------------------------------------------------------------------

class ApiError(SystemExit):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


class Firefly:
    def __init__(self, url: str, token: str, dry: bool):
        self.base = url.rstrip("/") + "/api/v1"
        self.token = token
        self.dry = dry
        self.created = {"accounts": 0, "categories": 0, "budgets": 0, "limits": 0, "bills": 0, "transactions": 0}

    def _req(self, method: str, path: str, body: dict | None = None, params: str = "") -> dict:
        req = urllib.request.Request(
            f"{self.base}{path}{params}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            raise ApiError(e.code, f"{method} {path} -> HTTP {e.code}: {detail}")

    def get_all(self, path: str) -> list[dict]:
        out, page = [], 1
        while True:
            d = self._req("GET", path, params=f"?limit=100&page={page}")
            out += d.get("data", [])
            if page >= d.get("meta", {}).get("pagination", {}).get("total_pages", 1):
                return out
            page += 1

    def post(self, path: str, body: dict, kind: str) -> dict:
        if self.dry:
            print(f"  [dry] POST {path} {body.get('name') or body.get('transactions', [{}])[0].get('description', '')}")
            return {"data": {"id": "0"}}
        d = self._req("POST", path, body)
        self.created[kind] += 1
        return d


# ---------------------------------------------------------------------------
# Fixture handling
# ---------------------------------------------------------------------------

def month_shift(date: dt.date, target_year: int, target_month: int) -> dt.date:
    last = calendar.monthrange(target_year, target_month)[1]
    return dt.date(target_year, target_month, min(date.day, last))


def prior_months(n: int, today: dt.date) -> list[tuple[int, int]]:
    """[(year, month)] for the current month and n-1 months before it, oldest first."""
    ys, ms = [], today.month
    y = today.year
    for _ in range(n):
        ys.append((y, ms))
        ms -= 1
        if ms == 0:
            ms, y = 12, y - 1
    return list(reversed(ys))


def build_transactions(rows: list[dict], months: list[tuple[int, int]], accounts: dict[str, dict]) -> list[dict]:
    """Turn fixture rows into Firefly transaction payloads for each target month."""
    txs = []
    for (y, m) in months:
        cycle_tag = f"sample-{y}{m:02d}"
        for r in rows:
            d0 = dt.date.fromisoformat(r["date"])
            d = month_shift(d0, y, m)
            amount = float(r["amount"])
            owning, opposing = r["owning_account"], r["opposing_account"]
            own = accounts[owning]
            opp = accounts.get(opposing)
            if opp is not None:
                src, dst = (owning, opposing) if amount < 0 else (opposing, owning)
                s_t, d_t = accounts[src]["type"], accounts[dst]["type"]
                if s_t == "asset" and d_t == "asset":
                    ttype = "transfer"
                elif d_t == "liabilities":
                    ttype = "withdrawal"
                else:  # liability -> asset
                    ttype = "deposit"
                leg = {"type": ttype, "source_id": accounts[src]["id"], "destination_id": accounts[dst]["id"]}
            elif amount < 0:
                leg = {"type": "withdrawal", "source_id": own["id"], "destination_name": opposing}
            else:
                leg = {"type": "deposit", "source_name": opposing, "destination_id": own["id"]}

            tags = [t.strip() for t in r["tags"].split(",") if t.strip()]
            tags = [str(y) if t.isdigit() and len(t) == 4 else t for t in tags]
            tags = [cycle_tag if t.startswith("sample-") else t for t in tags]
            notes = r["notes"].replace("sample.csv", f"sample-{y}{m:02d}.csv")
            leg.update({
                "date": d.isoformat(),
                "amount": f"{abs(amount):.2f}",
                "description": r["description"],
                "category_name": r["category"] or None,
                "tags": sorted(set(tags)),
                "notes": notes,
            })
            budget = CATEGORY_BUDGET.get(r["category"])
            if budget and leg["type"] == "withdrawal":
                leg["budget_name"] = budget
            txs.append({
                "error_if_duplicate_hash": False,
                "apply_rules": False,
                "fire_webhooks": False,
                "transactions": [leg],
            })
    return txs


# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", type=Path, help="dotenv-style file with FF_URL and FF_DEMO_PAT (e.g. .local/firefly-demo.env)")
    ap.add_argument("--months", type=int, default=2, help="how many months of the fixture to post, ending with the current month")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="proceed even if the user already has transactions")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.env:
        for ln in args.env.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    url, token = env.get("FF_URL", ""), env.get("FF_DEMO_PAT", "")
    if not url or not token:
        raise SystemExit("FF_URL and FF_DEMO_PAT are required (env or --env file)")

    ff = Firefly(url, token, args.dry_run)

    # Who am I, and is this really an empty user?
    about = ff._req("GET", "/about/user")
    email = about.get("data", {}).get("attributes", {}).get("email", "?")
    existing_tx = ff._req("GET", "/transactions", params="?limit=1").get("meta", {}).get("pagination", {}).get("total", 0)
    print(f"user: {email}   existing transactions: {existing_tx}")
    if existing_tx and not args.force:
        raise SystemExit("This user already has transactions. Refusing to seed a non-empty user without --force.")

    # Accounts (idempotent by name)
    have = {a["attributes"]["name"]: {"id": a["id"], "type": a["attributes"]["type"]} for a in ff.get_all("/accounts")}
    accounts: dict[str, dict] = {}
    for name, role, extra in ASSETS:
        if name in have:
            accounts[name] = have[name]; continue
        body = {"name": name, "type": "asset", "account_role": role, "currency_code": "CAD", "include_net_worth": True}
        if "opening_balance" in extra:
            body.update({"opening_balance": extra["opening_balance"], "opening_balance_date": "2025-01-01"})
        if role == "ccAsset":
            body.update({"credit_card_type": extra["credit_card_type"], "monthly_payment_date": extra["monthly_payment_date"]})
        d = ff.post("/accounts", body, "accounts")
        accounts[name] = {"id": d["data"]["id"], "type": "asset"}
    for name, ltype, interest, period, opening in LIABILITIES:
        if name in have:
            accounts[name] = have[name]; continue
        body = {"name": name, "type": "liability", "liability_type": ltype, "liability_direction": "debit",
                "interest": interest, "interest_period": period, "currency_code": "CAD", "include_net_worth": True}
        if opening:
            body.update({"opening_balance": opening, "opening_balance_date": "2025-01-01"})
        d = ff.post("/accounts", body, "accounts")
        accounts[name] = {"id": d["data"]["id"], "type": "liabilities"}
    print(f"accounts ready: {len(accounts)}")

    # Categories
    rows = list(csv.DictReader(FIXTURE.open(encoding="utf-8")))
    have_cat = {c["attributes"]["name"] for c in ff.get_all("/categories")}
    for cat in sorted({r["category"] for r in rows if r["category"]}):
        if cat in have_cat:
            continue
        ff.post("/categories", {"name": cat, "notes": CATEGORY_NOTES.get(cat)}, "categories")

    # Budgets + a limit for the current period
    today = dt.date.today()
    have_b = {b["attributes"]["name"]: b["id"] for b in ff.get_all("/budgets")}
    for name, atype, period, amount in BUDGETS:
        if name in have_b:
            continue
        d = ff.post("/budgets", {"name": name, "active": True, "auto_budget_type": atype,
                                 "auto_budget_currency_code": "CAD", "auto_budget_amount": amount,
                                 "auto_budget_period": period}, "budgets")
        bid = d["data"]["id"]
        if period == "monthly":
            start = today.replace(day=1)
            end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        else:
            start, end = dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
        if not args.dry_run:
            # Firefly creates the current-period limit itself when an auto-budget is set (observed on
            # 6.6.6); posting one explicitly then returns 422. Try, and accept "already exists".
            try:
                ff.post(f"/budgets/{bid}/limits", {"start": start.isoformat(), "end": end.isoformat(),
                                                   "amount": amount, "currency_code": "CAD"}, "limits")
            except ApiError as e:
                if e.code != 422:
                    raise

    # Subscriptions
    have_bill = {b["attributes"]["name"] for b in ff.get_all("/bills")}
    for name, mn, mx, freq, group, notes in BILLS:
        if name in have_bill:
            continue
        ff.post("/bills", {"name": name, "amount_min": mn, "amount_max": mx, "date": "2025-01-05",
                           "repeat_freq": freq, "skip": 0, "active": True, "currency_code": "CAD",
                           "notes": notes or None, "object_group_title": group}, "bills")

    # Transactions
    months = prior_months(args.months, today)
    txs = build_transactions(rows, months, accounts)
    print(f"posting {len(txs)} transactions across {', '.join(f'{y}-{m:02d}' for y, m in months)}")
    for i, tx in enumerate(txs, 1):
        ff.post("/transactions", tx, "transactions")
        if i % 10 == 0:
            print(f"  {i}/{len(txs)}")

    print("created:", json.dumps(ff.created))
    if args.dry_run:
        print("dry run — nothing was written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
