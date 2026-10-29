"""Rule-level contracts for sanitize/sanitize_pdf.py.

Each case is a miss or a false alarm found on an invented test corpus: an all-capitals mailing address, a lower-case postal code,
and --strict failing on an amount printed without thousands separators.
All values are invented.

    python -m pytest sanitize/test_sanitize_pdf_rules.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "sanitize_pdf.py"
sys.path.insert(0, str(SCRIPT.parent))
import sanitize_pdf  # noqa: E402


def sanitizer() -> sanitize_pdf.Sanitizer:
    return sanitize_pdf.Sanitizer(salt="fixed", detectors=sanitize_pdf.build_detectors(7))


@pytest.mark.parametrize("address", [
    "221 MAPLE GROVE WAY SW",        # all capitals, direction suffix
    "88 ELM CRES",                   # all capitals, abbreviated type
    "305 Cedar Ridge BLVD NE",       # title-case words, capital type
    "17 BIRCHWOOD Drive",            # capital words, title-case type
])
def test_an_address_line_in_capitals_or_mixed_case_is_redacted(address):
    s = sanitizer()
    out = s.scrub(f"Mail to: {address}\nCalgary AB")
    assert address not in out, out
    assert s.counts["street_address"] == 1


@pytest.mark.parametrize("postal", ["t4n 5e1", "t4n5e1", "T2n 1p4", "t2n-1p4"])
def test_a_lower_or_mixed_case_postal_code_is_redacted(postal):
    s = sanitizer()
    out = s.scrub(f"Calgary AB  {postal}\n")
    assert postal not in out, out
    assert s.counts["postal_code"] == 1


def test_ordinary_lower_case_words_after_a_number_are_not_an_address():
    text = "Split 3 ways; 2 way radio; 4 close calls; row 12 green"
    s = sanitizer()
    assert s.scrub(text) == text
    assert not s.counts


@pytest.mark.parametrize("amount", ["-1234567.89", "1234567.89", "$1234567", "+12345678.00"])
def test_strict_scan_does_not_flag_an_amount_without_thousands_separators(amount):
    s = sanitizer()
    out = s.scrub(f"2026-03-22  Large item  {amount}\n")
    assert amount in out, out
    assert s.residuals(out) == {}


def test_strict_scan_still_flags_a_long_digit_run_that_is_not_an_amount():
    assert sanitizer().residuals("Client Reference 900218374465\n") == {"long_digits": 1}
