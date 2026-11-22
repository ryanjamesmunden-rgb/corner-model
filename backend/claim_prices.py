"""A price for every claim the site makes, without anybody typing one.

THE GAP THIS CLOSES. The card that goes out Monday and Wednesday, the streak board, the
quick scan and perfect games are all frozen before kick-off and graded afterwards — and
almost none of them carry a price. history_export says it plainly: "only angles posted by
hand carry price and stake". So /results could report hit rates and nothing else, and a
board landing 86% on 1.25 shots cannot be told apart from one landing 60% on 2.10s.

The site has fetched bookmaker prices automatically since November (odds_feed.py), and
captures the last one before kick-off (fetch_odds --closing -> db.odds_closing). Nothing
joined either of them to the record. This does.

THREE PRICES, KEPT APART, because they answer three different questions:

  price        what YOU typed — the bet you actually took. Never overwritten here.
  post_price   the best fetched price at the moment the claim was frozen or posted.
               What a follower could have taken when they read it. Frozen with the claim
               and immutable, for the reason snapshot_value gives: re-pricing a claim
               later would flatter or misreport it.
  close_price  the last price captured before kick-off. What the market settled on. Read
               at grading time from db.odds_closing, or from the last pre-match fetch.

UNITS ARE REPORTED SEPARATELY AT EACH, never blended. A total mixing typed prices with
fetched ones would be a number about nothing in particular.

WHAT THIS REFUSES TO DO:
  - price an UNDER. The feed's under side is not stored (odds_feed.market_key says why),
    so there is no fetched under price to attach. Counted as unpriced, with the reason.
  - use a price fetched AFTER kick-off. A post-kick-off number is an in-play price for a
    game already under way, and grading a claim against it would be grading a different
    bet. The provider serves pre-match markets only, but the check is here anyway.
  - use a fetched price older than STALE_HOURS before the claim. A price from yesterday
    is not one a reader of today's post could have taken.

Pure functions, no database, so every rule here is testable on its own.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

import odds_feed

#: A fetched price older than this, relative to when the claim was made, was not
#: available to anybody reading the claim. The same twelve hours fetch_odds ages prices on.
STALE_HOURS = 12

#: The last pre-match fetch stands in for a closing price only if it was taken this close
#: to the off. Further out it is an opening-ish price, and calling it the close would
#: overstate how late the market was read.
CLOSE_FALLBACK_HOURS = 6

PRICE_KINDS = ("price", "post_price", "close_price")


def _ts(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def market_for(claim: dict):
    """(market key, why-not) for a claim, in the key spelling the feed stores."""
    return odds_feed.market_key(claim.get("subject") or "team", claim.get("is_home"),
                                claim.get("line"), claim.get("direction") or "over")


def post_price(claim: dict, feed_doc: Optional[dict], now: datetime) -> dict:
    """The fetched price available when the claim was made, or {} with no price.

    Returned as fields to merge onto the claim: post_price, post_book, post_fetched_at.
    `post_why` is set instead when there is no price, so an unpriced claim says why."""
    key, why = market_for(claim)
    if key is None:
        return {"post_why": why}
    if not feed_doc:
        return {"post_why": "no fetched prices for this fixture when it was posted"}
    ko = _ts(claim.get("kickoff"))
    if ko and now >= ko:
        return {"post_why": "posted after kick-off"}
    fetched = _ts(feed_doc.get("fetched_at"))
    if fetched is None or (now - fetched).total_seconds() > STALE_HOURS * 3600:
        return {"post_why": "the fetched price was more than 12 hours old"}
    p = (feed_doc.get("odds") or {}).get(key)
    if not p:
        return {"post_why": f"no book was quoting {key} when it was posted"}
    return {"post_price": p, "post_book": (feed_doc.get("books") or {}).get(key),
            "post_fetched_at": feed_doc.get("fetched_at")}


def close_price(claim: dict, closing_doc: Optional[dict],
                feed_doc: Optional[dict] = None) -> dict:
    """The last pre-match price for a claim's market, or {} with a reason.

    The closing capture is preferred: it is taken in the hour and a half before the off,
    and stamped with how long before. Failing that, the fixture's last hourly fetch counts
    if it was taken before kick-off and within CLOSE_FALLBACK_HOURS of it."""
    key, why = market_for(claim)
    if key is None:
        return {"close_why": why}
    if closing_doc:
        p = (closing_doc.get("odds") or {}).get(key)
        if p:
            return {"close_price": p, "close_book": (closing_doc.get("books") or {}).get(key),
                    "close_minutes_before": closing_doc.get("minutes_before_kickoff"),
                    "close_source": "closing capture"}
    ko = _ts(claim.get("kickoff"))
    fetched = _ts((feed_doc or {}).get("fetched_at"))
    if feed_doc and ko and fetched and fetched < ko \
            and (ko - fetched).total_seconds() <= CLOSE_FALLBACK_HOURS * 3600:
        p = (feed_doc.get("odds") or {}).get(key)
        if p:
            return {"close_price": p, "close_book": (feed_doc.get("books") or {}).get(key),
                    "close_minutes_before": round((ko - fetched).total_seconds() / 60, 1),
                    "close_source": "last pre-match fetch"}
    return {"close_why": "no price was captured before kick-off for this fixture"}


def _units(result: str, price, stake=1.0) -> Optional[float]:
    if not price or price <= 1.0:
        return None
    s = float(stake or 1.0)
    if result == "win":
        return (float(price) - 1.0) * s
    if result == "loss":
        return -s
    return None


def priced_summary(rows: List[dict], win: str = "win", loss: str = "loss") -> dict:
    """Units at each of the three prices, each over its OWN priced rows.

    Every block carries `priced` and `unpriced`, so "+6.2u" is never read without the
    denominator it was computed over. ROI is per unit staked.

    CLV (`clv_mean`) is over rows that have BOTH a post price and a close price: did the
    price at posting beat the price at the off. It is the one number here that does not
    need hundreds of games to mean something."""
    out = {}
    settled = [r for r in rows if r.get("result") in (win, loss)]
    for kind in PRICE_KINDS:
        units, staked, priced = 0.0, 0.0, 0
        for r in settled:
            res = "win" if r["result"] == win else "loss"
            stake = float(r.get("stake") or 1.0) if kind == "price" else 1.0
            u = _units(res, r.get(kind), stake)
            if u is None:
                continue
            units += u
            staked += stake
            priced += 1
        out[kind] = {"priced": priced, "unpriced": len(settled) - priced,
                     "units": round(units, 2) if priced else None,
                     "roi": round(units / staked * 100, 1) if staked else None}
    clvs = [odds_feed.clv_percent(r.get("post_price"), r.get("close_price")) for r in rows]
    clvs = [c for c in clvs if c is not None]
    out["clv"] = {"measured": len(clvs),
                  "mean": round(sum(clvs) / len(clvs), 2) if clvs else None,
                  "beat_close": sum(1 for c in clvs if c > 0) if clvs else None}
    return out


def attach_close(rows: List[dict], closing: Dict[str, dict],
                 feed: Dict[str, dict]) -> List[dict]:
    """Each graded row with its close price merged on (rows without a fixture are left)."""
    out = []
    for r in rows:
        fid = r.get("fixture_id")
        if not fid:
            out.append({**r, "close_why": "no fixture recorded on the claim"})
            continue
        out.append({**r, **close_price(r, closing.get(fid), feed.get(fid))})
    return out
