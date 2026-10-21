"""Offline: did the MISMATCH board's picks actually land, and was its probability honest?

The mismatch screen is the one board with no run behind it. A streak says "this side has
cleared this line five times running"; a chase says "this side goes behind and chases".
A mismatch says only that two averages are both above their league's — a side that wins
corners drawn against a defence that concedes them — and prices the midpoint. That makes
it the board most exposed to a bad lambda, because lambda is the entire claim.

WHAT THIS ANSWERS, and nothing had:

  1. Of the fixtures the board would have shown, how many cleared the line it printed.
  2. Whether the printed probability was true — hit rate minus the model's own mean
     probability. A board can be profitable and dishonest, or honest and unprofitable,
     and the two failures need different fixes.
  3. THE SPLIT THAT PROMPTED THIS: home rows against away rows. The home projection is
     known to run hot (+1.9 corners over 115 graded picks, +1.4 over a filled-in sheet,
     and every home price on the current board flips from value to loss once it is taken
     off). A mismatch line is round(lambda) - 1, so an inflated lambda raises the LINE as
     well as the probability — it does not merely overstate a fixed claim, it quietly
     moves the bet to a harder one. If that is real, home mismatch rows should show a
     worse residual than away rows, and this is the measurement that says so.

WALK-FORWARD, AND THAT IS THE WHOLE DIFFICULTY. Every average here is rebuilt from the
fixtures BEFORE each kick-off, never from the team documents as they stand today — those
contain the result being predicted. The league average each side is measured against is
also a running one, for the same reason. Replaying a board with hindsight in it produces
a hit rate that means nothing, and it means nothing in the flattering direction.

Reads db.fixture_stats only. Writes nothing.
"""
import asyncio
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from server import V3_BLOCKED_WEIGHT, model_lambda, nb_ge

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

WINDOW = 10
# Same bar as BOARD_MIN_MISMATCH_GAMES in server.py. A mismatch is judged on sample
# because it has no run to be judged on, so the harness must not be more permissive than
# the board or it will measure rows the board would never have printed.
MIN_GAMES = 6
MIN_VENUE_GAMES = 3
MISMATCH_EDGE = 1.1      # both sides must clear their league average by this much


def avg(d):
    return sum(d) / len(d) if d else 0.0


def rate(hits, n):
    return (hits / n * 100) if n else 0.0


async def load_matches(league_id=None):
    q = {} if not league_id or league_id == "all" else {"league_id": league_id}
    matches = await db.fixture_stats.find(q, {"_id": 0}).to_list(60000)
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    return matches


def build_rows(matches):
    """Replay every finished fixture as the mismatch board would have seen it beforehand."""
    if not matches:
        return []

    shots = [m.get(f"{s}_shots", 0) for m in matches for s in ("home", "away")]
    lg_shots = (sum(shots) / len(shots)) if shots else 0.0
    blocked = [m[f"{s}_blocked_shots"] for m in matches for s in ("home", "away")
               if m.get(f"{s}_blocked_shots") is not None]
    lg_blocked = (sum(blocked) / len(blocked)) if blocked else 0.0

    cf = defaultdict(lambda: deque(maxlen=WINDOW))     # corners for, pooled
    ca = defaultdict(lambda: deque(maxlen=WINDOW))     # corners against, pooled
    sf = defaultdict(lambda: deque(maxlen=WINDOW))
    fh = defaultdict(lambda: deque(maxlen=WINDOW))
    bl = defaultdict(lambda: deque(maxlen=WINDOW))
    vcf = defaultdict(lambda: deque(maxlen=WINDOW))    # ...and venue-split, which is
    vca = defaultdict(lambda: deque(maxlen=WINDOW))    # how production prices
    vsf = defaultdict(lambda: deque(maxlen=WINDOW))
    vfh = defaultdict(lambda: deque(maxlen=WINDOW))

    # The league average each side is compared against, accumulated as the replay runs.
    # Using today's figure would leak the season back into every fixture in it.
    lg_sum = defaultdict(float)
    lg_n = defaultdict(int)

    rows = []
    for m in matches:
        h, a = m.get("home_id"), m.get("away_id")
        lid = m.get("league_id")
        if h is None or a is None:
            continue
        for team, opp, side, actual in ((h, a, "home", m.get("home_corners")),
                                        (a, h, "away", m.get("away_corners"))):
            if actual is None:
                continue
            opp_side = "away" if side == "home" else "home"
            tv, ov = vcf[(team, side)], vca[(opp, opp_side)]
            if len(tv) < MIN_VENUE_GAMES or len(ov) < MIN_VENUE_GAMES:
                continue
            if len(cf[team]) < MIN_GAMES or len(ca[opp]) < MIN_GAMES:
                continue
            lg_avg = (lg_sum[lid] / lg_n[lid]) if lg_n[lid] else 5.0

            team_for, opp_conc = avg(tv), avg(ov)
            # THE GATE, exactly as _all_mismatches applies it.
            if not (team_for >= lg_avg * MISMATCH_EDGE and opp_conc >= lg_avg * MISMATCH_EDGE):
                continue

            def vform(pooled, venue_pool):
                return avg(venue_pool) if venue_pool else avg(pooled)

            lam = model_lambda("v3", team_for, opp_conc,
                               vform(sf[team], vsf[(team, side)]), lg_shots,
                               vform(fh[team], vfh[(team, side)]),
                               avg(bl[team]) if len(bl[team]) >= MIN_GAMES else 0.0,
                               lg_blocked, V3_BLOCKED_WEIGHT)
            line = max(3, round(lam) - 1)
            rows.append({
                "date": m["date"], "league_id": lid,
                "team_id": team, "opp_id": opp, "venue": side,
                "team_for": team_for, "opp_conceded": opp_conc, "lg_avg": lg_avg,
                "lambda": lam, "line": line, "prob": nb_ge(line, lam),
                "actual": actual, "hit": actual >= line,
                "margin": actual - line,
            })

        # ...and only now does this fixture become history for the next one.
        for team, opp, side, c_for, c_ag in ((h, a, "home", m.get("home_corners"), m.get("away_corners")),
                                             (a, h, "away", m.get("away_corners"), m.get("home_corners"))):
            opp_side = "away" if side == "home" else "home"
            if c_for is not None:
                cf[team].append(c_for)
                vcf[(team, side)].append(c_for)
                lg_sum[lid] += c_for
                lg_n[lid] += 1
            if c_ag is not None:
                ca[team].append(c_ag)
                vca[(team, side)].append(c_ag)
            s = m.get(f"{side}_shots")
            if s is not None:
                sf[team].append(s)
                vsf[(team, side)].append(s)
            b = m.get(f"{side}_blocked_shots")
            if b is not None:
                bl[team].append(b)
            g = 1.0 if (m.get(f"{side}_fh_goals") or 0) >= 1 else 0.0
            fh[team].append(g)
            vfh[(team, side)].append(g)
    return rows


def summarise(rows, label):
    """Hit rate against the model's own mean probability — the residual is the finding."""
    if not rows:
        print(f"  {label:<22} no qualifying rows")
        return
    n = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    said = sum(r["prob"] for r in rows) / n * 100
    got = rate(hits, n)
    lam = sum(r["lambda"] for r in rows) / n
    act = sum(r["actual"] for r in rows) / n
    print(f"  {label:<22} {n:>5} rows  {hits:>4} hit  {got:5.1f}% actual  "
          f"{said:5.1f}% model  residual {got - said:+5.1f}pt   "
          f"lambda {lam:5.2f} vs {act:5.2f} actual ({act - lam:+.2f})")


async def run(since=None, until=None, league_id=None, show=200):
    # Defaults to the current month so the harness mode needs no argument — and so a
    # re-run next month asks about next month rather than reprinting this one.
    if since is None:
        since = datetime.now(timezone.utc).strftime("%Y-%m-01")
    matches = await load_matches(league_id)
    rows = build_rows(matches)
    print(f"Replayed {len(matches)} finished fixtures -> {len(rows)} mismatch rows in all.\n")

    def in_window(r):
        d = r["date"][:10]
        return (not since or d >= since) and (not until or d <= until)

    window = [r for r in rows if in_window(r)]
    if not window:
        print("No mismatch rows in that window.")
        return

    leagues = {l["league_id"]: l["name"]
               for l in await db.leagues.find({}, {"_id": 0}).to_list(200)}
    names = {t["team_id"]: t["name"]
             for t in await db.teams.find({}, {"_id": 0, "team_id": 1, "name": 1}).to_list(4000)}

    print(f"EVERY MISMATCH FIXTURE {since or 'start'} to {until or 'now'} "
          f"({len(window)} rows)\n")
    print(f"{'date':<11} {'league':<20} {'team':<22} {'v':<1} {'opponent':<22} "
          f"{'at':<4} {'line':>4} {'lam':>5} {'said':>5} {'got':>4} {'by':>4}  result")
    for r in sorted(window, key=lambda r: r["date"])[:show]:
        print(f"{r['date'][:10]:<11} {leagues.get(r['league_id'], '?')[:20]:<20} "
              f"{names.get(r['team_id'], '?')[:22]:<22} v "
              f"{names.get(r['opp_id'], '?')[:22]:<22} "
              f"{r['venue']:<4} {r['line']:>4} {r['lambda']:>5.2f} "
              f"{r['prob']*100:>4.0f}% {r['actual']:>4} {r['margin']:>+4} "
              f" {'WON' if r['hit'] else 'lost'}")
    if len(window) > show:
        print(f"... {len(window) - show} more")

    print(f"\nHOW THEY LANDED\n")
    summarise(window, "all")
    summarise([r for r in window if r["venue"] == "home"], "home rows")
    summarise([r for r in window if r["venue"] == "away"], "away rows")
    print()
    for line in sorted({r["line"] for r in window}):
        summarise([r for r in window if r["line"] == line], f"line {line}+")

    print(f"\nTHE SAME BOARD OVER ALL CACHED HISTORY (the window above is a small sample)\n")
    summarise(rows, "all")
    summarise([r for r in rows if r["venue"] == "home"], "home rows")
    summarise([r for r in rows if r["venue"] == "away"], "away rows")

    home = [r for r in rows if r["venue"] == "home"]
    away = [r for r in rows if r["venue"] == "away"]
    if home and away:
        hres = rate(sum(1 for r in home if r["hit"]), len(home)) - \
            sum(r["prob"] for r in home) / len(home) * 100
        ares = rate(sum(1 for r in away if r["hit"]), len(away)) - \
            sum(r["prob"] for r in away) / len(away) * 100
        herr = sum(r["lambda"] - r["actual"] for r in home) / len(home)
        aerr = sum(r["lambda"] - r["actual"] for r in away) / len(away)
        print(f"\nVENUE GAP  residual home {hres:+.1f}pt vs away {ares:+.1f}pt "
              f"— home is {abs(hres - ares):.1f}pt "
              f"{'worse' if hres < ares else 'better'}")
        print(f"           lambda error home {herr:+.2f} corners vs away {aerr:+.2f} "
              f"(positive = the model projected more corners than were won)")


def main():
    args = sys.argv[1:]

    def opt(flag, default=None, cast=str):
        return cast(args[args.index(flag) + 1]) if flag in args else default

    asyncio.run(run(since=opt("--since"), until=opt("--until"),
                    league_id=opt("--league"), show=opt("--show", 200, int)))


if __name__ == "__main__":
    main()
