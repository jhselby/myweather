"""Rolling analysis-window helper.

Replaces hardcoded WIN_A_LO/WIN_A_HI/... date-string literals that
went stale every ~4 days and had to be slid forward by hand. The
fossil-window audit in build_executive_summary.py scans for date
literals in WIN_* assignments; scripts that use this helper have
none, so they can never fossilize.

Every fossil-flagged script had the same shape:
    recent halves window, prior halves window, combined full window.
Pass different day counts when a script needs a shorter shape (e.g.
a post-ship watch that only has ~5d of clean data).

Usage:
    from _windows import rolling_windows
    WIN = rolling_windows()  # 15d/15d/30d anchored at today 00:00
    # WIN.A_LO, WIN.A_HI, WIN.B_LO, WIN.B_HI, WIN.FULL_LO, WIN.FULL_HI
"""
import datetime as _dt
from typing import NamedTuple, Optional


class Windows(NamedTuple):
    A_LO: str
    A_HI: str
    B_LO: str
    B_HI: str
    FULL_LO: str
    FULL_HI: str


_FMT = "%Y-%m-%dT%H:%M"


def rolling_windows(
    recent_days: int = 15,
    prior_days: int = 15,
    end: Optional[_dt.date] = None,
) -> Windows:
    """Return WIN_* string literals anchored at midnight of `end` (default today).

    A = [end - recent_days, end)         — recent half
    B = [A_LO - prior_days, A_LO)        — prior half
    FULL = [B_LO, A_HI)                  — combined
    """
    end = end or _dt.date.today()
    a_hi = _dt.datetime.combine(end, _dt.time(0, 0))
    a_lo = a_hi - _dt.timedelta(days=recent_days)
    b_hi = a_lo
    b_lo = b_hi - _dt.timedelta(days=prior_days)
    return Windows(
        A_LO=a_lo.strftime(_FMT),
        A_HI=a_hi.strftime(_FMT),
        B_LO=b_lo.strftime(_FMT),
        B_HI=b_hi.strftime(_FMT),
        FULL_LO=b_lo.strftime(_FMT),
        FULL_HI=a_hi.strftime(_FMT),
    )
