"""Offline: why is each pending slip still pending?

WHY THIS EXISTS. "Pending" on the Bets page means one of two completely different things
and the page cannot tell them apart: the match has not been played, or the match was
played and the settler could not grade it. The first is correct and needs nothing. The
second is a slip that will sit there for ever, because nothing in the settler ever gives
up, retries differently, or logs — `bet_outcome` returns None for every uncertainty and
None means pending.

So a reader looking at a wall of pending rows has no way to know whether the site is
working. This names a reason for every one of them.

THE REASONS, in the order they are checked, because an earlier one makes the later ones
moot:

  not played yet        kick-off is in the future. Correct, and the expected answer for
                        most of them. Counted separately so it cannot pad the bad news.
  no provider id        the slip carries no `api_fixture_id` and none is recoverable from
                        `fixture_id`. Unsettleable by construction — see _api_fixture_id.
                        A synthesized fallback fixture lands here and SHOULD: it is an
                        invented pairing, not a real match.
  market unparseable    `parse_market_key` cannot read `market_key`. A slip written by a
                        version of the site that spelled a market differently.
  corners not synced    the fixture id resolves but db.fixture_stats holds nothing for it.
                        This is the one that matters: sync_real caches the CURRENT SEASON
                        of the leagues it is configured for, so a finished match outside
                        that coverage never gets corners and the slip waits for data that
                        is never coming. Unlike settlement.py, which fetches on demand and
                        voids after MISSING_DATA_VOID_HOURS, the bet settler only reads the
                        cache and has no give-up path at all.
  corners missing       there IS a cached fixture but a corner count on it is null.
  would settle now      everything needed is present. Means the settler has not run since
                        the data arrived — it runs on Bets page load, so this should clear
                        by itself and is worth knowing about only if it does not.

AND IT CHECKS THE KEY TYPE, WHICH IS ITS OWN CATEGORY OF BUG. db.fixture_stats is keyed
by the provider's fixture id exactly as the provider sends it: a JSON number, so an int in
Mongo. A slip that carries `api_fixture_id` has the same int copied onto it and matches. A
slip that has to RECOVER the id by stripping the league prefix off `fixture_id` gets a
STRING back, and Mongo's `$in` does not equate "12345" with 12345 — so that slip silently
matches nothing, for ever, while looking exactly like a match that has not kicked off.
`key_type_mismatch` counts those separately from `corners not synced`, because the two
have opposite fixes: one is a bug here, the other is missing data.

HOURS SINCE KICK-OFF IS PRINTED ON EVERY STALE ROW, because it is the number that says
whether a reason is a transient or a permanent. Corners arriving late is normal; corners
absent four days later is not.

Reads db.bets and db.fixture_stats. No API calls, no writes — it explains the state, it
does not repair it.

Run: python audit_bets.py
     python audit_bets.py --user usr_abc123
     python audit_bets.py --all          (include settled slips in the totals)
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import parse_market_key

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

# A match is not "late" the moment it starts. Ninety minutes plus half-time plus stoppage
# plus the provider's own lag: before this much has passed, no corner count is expected and
# a missing one says nothing.
SETTLE_GRACE_HOURS = 3
# What settlement.py gives a pick before voiding it for missing data. Restated here only to
# label rows the BET settler has no equivalent rule for — it never voids anything.
PICK_VOID_HOURS = 48

REASONS = ("not played yet", "no provider id", "market unparseable",
           "key type mismatch", "corners not synced", "corners missing",
           "would settle now")


def parse_dt(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hours_since(iso, now):
    dt = parse_dt(iso)
    return None if dt is None else (now - dt).total_seconds() / 3600.0


def raw_id(bet):
    """The id AS THE SLIP STORES IT, with no normalising — deliberately.

    NOT server._api_fixture_id, and the difference is the point. That function now coerces
    the id to the int the cache is keyed by, which is the fix. This one reproduces what the
    slip actually holds, so the audit can still say WHY a slip sat pending: a string where
    an int was needed. Importing the fixed version would make this file agree with itself
    and report every historical row as healthy.
    """
    if bet.get("api_fixture_id"):
        return bet["api_fixture_id"]
    fid, lid = str(bet.get("fixture_id") or ""), str(bet.get("league_id") or "")
    if lid and fid.startswith(lid + "-"):
        return fid[len(lid) + 1:] or None
    return None


def stats_key(value):
    """The key db.fixture_stats is actually keyed by: the provider's id as an int.

    The whole point of this function is that "12345" and 12345 are different keys to Mongo.
    A non-numeric id is passed through unchanged — a synthesized fallback fixture has one,
    and it is supposed to match nothing.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if not s:
        return None
    return int(s) if s.isdigit() else s


def why_pending(bet, stats_by_key, now, grace_hours=SETTLE_GRACE_HOURS):
    """(reason, detail) for one pending slip. Pure: every input is passed in.

    `stats_by_key` must be keyed by stats_key(), i.e. normalised — otherwise this function
    would reproduce the very type bug it is here to detect.
    """
    kickoff = parse_dt(bet.get("kickoff"))
    since = hours_since(bet.get("kickoff"), now)
    if kickoff is None:
        # No kick-off on the slip at all. Not classifiable as early or late, and worth
        # saying rather than folding into one of the data reasons.
        return "no provider id" if raw_id(bet) is None else "corners not synced", \
               "no kickoff stored on the slip"
    if since is not None and since < grace_hours:
        return "not played yet", f"kick-off {-since:.1f}h away" if since < 0 else \
                                 f"kicked off {since:.1f}h ago, inside the {grace_hours}h grace"

    raw = raw_id(bet)
    if raw is None:
        return "no provider id", f"fixture_id={bet.get('fixture_id')!r} is not recoverable"
    if parse_market_key(bet.get("market_key")) is None:
        return "market unparseable", f"market_key={bet.get('market_key')!r}"

    key = stats_key(raw)
    doc = stats_by_key.get(key)
    if doc is None:
        return "corners not synced", f"nothing cached for fixture {key} ({since:.0f}h ago)"
    # The type check, and it must come AFTER confirming the data exists: a mismatch only
    # costs something when there is a document the slip should have matched and did not.
    if not isinstance(raw, int) and isinstance(key, int):
        return "key type mismatch", (f"slip carries {raw!r} (str), fixture_stats is keyed "
                                     f"{key!r} (int) — $in matches neither way")
    if doc.get("home_corners") is None or doc.get("away_corners") is None:
        return "corners missing", f"cached fixture {key} has a null corner count"
    return "would settle now", (f"{doc.get('home_corners')}-{doc.get('away_corners')} "
                                f"cached; settler has not run since")


def classify(bets, stats_by_key, now):
    """Every pending slip grouped by reason, each group newest kick-off first."""
    out = defaultdict(list)
    for b in bets:
        reason, detail = why_pending(b, stats_by_key, now)
        out[reason].append((b, detail))
    for rows in out.values():
        rows.sort(key=lambda r: r[0].get("kickoff") or "", reverse=True)
    return out


def verdict(groups, now):
    """What the counts mean, naming only a cause the split supports."""
    broken = {r: len(groups.get(r) or []) for r in
              ("key type mismatch", "corners not synced", "corners missing",
               "no provider id", "market unparseable")}
    stuck = sum(broken.values())
    if not stuck:
        waiting = len(groups.get("not played yet") or [])
        ready = len(groups.get("would settle now") or [])
        if ready:
            return (f"{ready} slip(s) have everything needed and are not graded. The settler "
                    f"runs on Bets page load, so open the page once — if they stay pending "
                    f"after that, settle_pending_bets is not being reached.")
        return (f"Nothing is stuck. All {waiting} pending slip(s) are waiting on matches "
                f"that have not been played, which is what pending is supposed to mean.")
    worst = max(broken, key=lambda r: broken[r])
    if worst == "key type mismatch":
        return (f"{broken[worst]} slip(s) sat pending on a KEY TYPE BUG, not on missing "
                f"data: the id stored on the slip is a string and fixture_stats is keyed by "
                f"an int, so the join matched nothing. The corners are already cached — "
                f"_api_fixture_id now normalises, so these grade themselves on the next "
                f"Bets page load. Nothing to fetch and nothing to void. If they are still "
                f"here after a page load, the fix is not deployed.")
    if worst == "corners not synced":
        return (f"{broken[worst]} slip(s) are waiting on corner data that is not in the "
                f"cache. sync_real covers the current season of its configured leagues, so "
                f"check whether these fixtures are in one. The bet settler — unlike "
                f"settlement.py — never fetches on demand and never voids after "
                f"{PICK_VOID_HOURS}h, so these wait for ever by design rather than by fault.")
    return (f"{stuck} slip(s) are stuck, most of them '{worst}'. Read the rows above: each "
            f"reason has a different fix and the counts say which one is worth doing.")


async def run(user_id=None, include_settled=False):
    now = datetime.now(timezone.utc)
    q = {} if include_settled else {"status": "pending"}
    if user_id:
        q["user_id"] = user_id
    bets = await db.bets.find(q, {"_id": 0}).to_list(5000)

    print("BET AUDIT — why is each pending slip still pending?")
    print("(reads db.bets and db.fixture_stats; no API calls, no writes)\n")
    print(f"slips matched: {len(bets)}   user={user_id or 'all'}")
    if not bets:
        print("\nNo slips. Nothing to explain.")
        return

    by_status = Counter(b.get("status") or "?" for b in bets)
    print("by status: " + "  ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    pending = [b for b in bets if (b.get("status") or "pending") == "pending"]
    if not pending:
        print("\nNothing pending.")
        return

    # BOTH TYPES ARE FETCHED DELIBERATELY. Asking for only the normalised key would hide
    # the very mismatch this is measuring, and asking for only the raw one is the bug.
    raw_ids = [raw_id(b) for b in pending]
    keys = {stats_key(i) for i in raw_ids if i is not None} - {None}
    wanted = list(keys) + [str(k) for k in keys if isinstance(k, int)]
    docs = await db.fixture_stats.find({"_id": {"$in": wanted}}, {}).to_list(8000) \
        if wanted else []
    stats_by_key = {stats_key(d["_id"]): d for d in docs}
    str_keyed = sum(1 for d in docs if not isinstance(d["_id"], int))
    print(f"pending: {len(pending)}   distinct fixtures: {len(keys)}   "
          f"cached: {len(docs)}" + (f"   ({str_keyed} string-keyed)" if str_keyed else ""))

    groups = classify(pending, stats_by_key, now)
    print(f"\n{'reason':>20}  {'n':>4}")
    for reason in REASONS:
        rows = groups.get(reason) or []
        if rows:
            print(f"{reason:>20}  {len(rows):4}")

    for reason in REASONS:
        rows = groups.get(reason) or []
        if not rows or reason == "not played yet":
            continue
        print(f"\n{reason.upper()}  ({len(rows)})")
        for b, detail in rows[:15]:
            since = hours_since(b.get("kickoff"), now)
            age = f"{since:.0f}h ago" if since is not None else "no kickoff"
            print(f"  {(b.get('kickoff') or '?')[:16]}  {age:>10}  "
                  f"{b.get('home_name')} v {b.get('away_name')}  "
                  f"{b.get('market_label') or b.get('market_key')}")
            print(f"       {detail}")
        if len(rows) > 15:
            print(f"  ... and {len(rows) - 15} more")

    waiting = groups.get("not played yet") or []
    if waiting:
        soonest = min((b.get("kickoff") or "z" for b, _ in waiting))
        print(f"\nNOT PLAYED YET ({len(waiting)}) — correct. Earliest kick-off {soonest[:16]}.")

    print(f"\n{'=' * 78}\nVERDICT\n{'=' * 78}")
    print(f"  {verdict(groups, now)}")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(user_id=opt("--user"), include_settled="--all" in args))


if __name__ == "__main__":
    main()
