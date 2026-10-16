"""The strange things in the data — superlatives, extremes and freaks, with names on them.

WHY THIS EXISTS. The daily X post had five candidates and four of them were the same
sentence: "N teams playing in the next 3 days have won 4+ corners in each of their last 5
or more", with the threshold moved. breadth, today, deep and high differ by a number, not
by a claim, and an account that posts the same sentence every morning is one people learn
to scroll past however true the number is. The complaint that produced this file was
"generic tweets with no variance", and it was correct.

A THRESHOLD IS NOT AN ANGLE. The fix is not more thresholds; it is claims of different
SHAPES — a single match, a season-long floor, a venue split, a league against another
league, a team that keeps winning corners and losing. Each finding below answers a
different question, so two of them can never read as each other.

AND THE CLUBS ARE THE HOOK. This site holds 28 leagues across 20 countries, from the
Premier League down to League Two and out to Japan, Argentina and Australia. "A League Two
side wins more corners than anyone in Serie A" is interesting precisely because of who it
names, and it is a fact about games already played rather than a tip. The old rule here
was NOBODY IS NAMED, on the argument that the names are the paid product. That rule still
holds for the BOARD — who to back on Saturday is the thing people pay for — and it does
not apply to any of this, because none of these is a selection. A record of what Vejle did
in August sells nothing and gives nothing away.

FOUR RULES, AND THEY ARE WHAT KEEP THIS HONEST:

  1. BACKWARD-LOOKING ONLY. Every number here is drawn from matches already played. There
     is no projection, no probability and no upcoming fixture anywhere in this file. That
     is also why naming teams is safe: "Vejle have won 7.9 corners a game" is a record,
     and it becomes a tip only if someone writes "so back them", which is why the wording
     lives in a separate module with its own tests.

  2. REAL MATCHES ONLY, NEVER `matches`. sync_real pads a thin team with `_synth_matches`
     — gaussian noise around its average — so `matches` can contain games that were never
     played. Those are legitimate for a model that needs a prior and are poison for a
     published fact: this file would cheerfully announce a 15-corner rout that nobody
     attended. So it reads `real_matches` and nothing else, and a team without enough of
     them holds no records.

  3. EVERY SUPERLATIVE IS BOUNDED TO THIS SITE. "The widest home/away split in Europe" is
     a claim about leagues we do not hold and cannot check. "The widest of the 548 teams
     on this site" is true, is checkable, and is a better hook for exactly that reason.
     Every finding therefore carries its own pool size, and the wording module is required
     to print it.

  4. EVERY CLAIM CARRIES ITS DENOMINATOR. A floor of 5 corners over 20 games is a
     remarkable thing; over 3 games it is a Tuesday. `games` rides along on every record
     and `MIN_GAMES` keeps the thin ones out of the comparison entirely.

WHAT THIS DELIBERATELY DOES NOT DO: invent club trivia. Founding dates, nicknames, ground
oddities and who-hates-whom are not in this database, and a site whose whole argument is
"our numbers are checkable" cannot start printing colour it cannot source. Everything here
is computed from match records we hold. That is a narrower pool of facts than the internet
has, and it is the only pool that comes with evidence attached.

NUMBERS OUT, NOT SENTENCES. Same split as every other board here: the backend returns
records and frontend/src/lib/oddityPosts.js writes the English. Rendering prose here would
be a second copy of a format that already exists in a tested module, and a second copy is
how two of them drift.
"""
from collections import defaultdict

# A team needs this many real matches before it can hold a record. Ten is the point at
# which a season average stops being three good nights, and it is also roughly half of
# sync_real's 20-match cap, so a mid-season team still qualifies.
MIN_GAMES = 10

# Per venue, for the home/away split. Lower than MIN_GAMES because a 20-game sample splits
# into roughly 10 and 10, and demanding 10 of each would answer with almost nobody.
MIN_VENUE_GAMES = 5

# A league needs this many team-games before its average is worth comparing to another's.
MIN_LEAGUE_GAMES = 60

# THE STIFFEST BAR HERE, AND ONLY FOR THE STRONGEST CLAIM. `punching_up` says a
# lower-division side out-corners an entire top flight, which is the biggest assertion in
# this file and the one most worth getting wrong. The first real run made it on a team
# with exactly ten games — a month of football — and went on to say they would top 19 of
# the 20 top flights on the site. That may well be true and ten games cannot show it.
PUNCH_MIN_GAMES = 15


def games_of(team):
    """The real match record, and only that. See rule 2 — `matches` may be synthetic."""
    return team.get("real_matches") or []


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def _label(team, leagues=None, meta=None):
    """Who this is, with enough around it to be recognisable to someone who has not heard
    of them — which, across 28 leagues, is most readers for most teams."""
    lid = team.get("league_id") or ""
    info = (meta or {}).get(lid) or {}
    return {
        "team": team.get("name") or "",
        "team_id": team.get("team_id"),
        "league_id": lid,
        "league": (leagues or {}).get(lid) or info.get("name") or "",
        "country": info.get("country") or "",
        "tier": info.get("tier"),
    }


# ---------------------------------------------------------------------------
# Single matches
# ---------------------------------------------------------------------------

def _match_records(teams, leagues, meta):
    """The three one-match extremes, found in a single pass.

    THEY SHARE A PASS BECAUSE THEY OFTEN SHARE A GAME. A 16-1 corner count is both the
    biggest rout and, usually, the biggest haul, and three separate scans would happily
    report the same match three times under three headings — which reads as one fact
    padded out, the exact failure this file exists to end. Found together, the caller can
    see the collision and drop the duplicates; see `survey`.

    Each match is seen TWICE, once from each side, because both teams carry it in their
    own record. That is fine for the rout and the haul, which are one-sided claims. For
    the combined total it means the same game competes with itself, which changes nothing
    about which game wins.
    """
    rout = haul = wildest = None
    for t in teams:
        gs = games_of(t)
        if not gs:
            continue
        who = _label(t, leagues, meta)
        for m in gs:
            cf, ca = m.get("corners_for"), m.get("corners_against")
            if cf is None or ca is None:
                continue
            row = {**who, "opponent": m.get("opponent") or "", "date": m.get("date"),
                   "home": bool(m.get("home")), "corners_for": cf, "corners_against": ca,
                   "goals_for": m.get("goals_for"), "goals_against": m.get("goals_against")}
            if rout is None or (cf - ca) > (rout["corners_for"] - rout["corners_against"]):
                rout = {**row, "margin": cf - ca}
            if haul is None or cf > haul["corners_for"]:
                haul = row
            if wildest is None or (cf + ca) > (wildest["corners_for"] + wildest["corners_against"]):
                wildest = {**row, "total": cf + ca}
    if rout is not None:
        rout["margin"] = rout["corners_for"] - rout["corners_against"]
    if wildest is not None:
        wildest["total"] = wildest["corners_for"] + wildest["corners_against"]
    return rout, haul, wildest


# ---------------------------------------------------------------------------
# Season-long team records
# ---------------------------------------------------------------------------

def _team_rows(teams, leagues, meta, min_games=MIN_GAMES):
    """One summary row per team with enough record to hold a record.

    Built once and reused by every finding below, because each of them is a different
    `max` over the same table and recomputing it per finding would walk the collection
    nine times for one answer.
    """
    rows = []
    for t in teams:
        gs = [m for m in games_of(t)
              if m.get("corners_for") is not None and m.get("corners_against") is not None]
        if len(gs) < min_games:
            continue
        cf = [m["corners_for"] for m in gs]
        ca = [m["corners_against"] for m in gs]
        home = [m for m in gs if m.get("home")]
        away = [m for m in gs if not m.get("home")]
        goals = [m["goals_for"] for m in gs if m.get("goals_for") is not None]
        # THE FLOOR AND THE CEILING ARE MEASURED OVER A FIXED WINDOW, and every other
        # number here is not. The reason is that a minimum and a maximum are EXTREME
        # ORDER STATISTICS: the more games you add, the likelier one of them is low, so a
        # team with ten games on record will out-floor a team with twenty for no reason
        # except having played half as much. The first real run of this printed exactly
        # that — a side with ten games held the highest floor on the site, and the
        # comparison it won was not a fair one.
        #
        # An average does not have that problem, which is why only these two are
        # windowed. Everybody is judged on their most recent `min_games`, so the
        # denominator in the post is the same for every team it could have named.
        window = gs[-min_games:]
        wcf = [m["corners_for"] for m in window]
        rows.append({
            **_label(t, leagues, meta),
            "games": len(gs),
            "for_avg": _avg(cf), "against_avg": _avg(ca),
            "floor": min(wcf), "ceiling": max(wcf), "window": len(window),
            "home_avg": _avg([m["corners_for"] for m in home]) if len(home) >= MIN_VENUE_GAMES else None,
            "away_avg": _avg([m["corners_for"] for m in away]) if len(away) >= MIN_VENUE_GAMES else None,
            "home_games": len(home), "away_games": len(away),
            "goals_avg": _avg(goals) if len(goals) == len(gs) else None,
            # How many games they finished with more corners than the opponent. A draw on
            # corners counts as neither, the same way a push is not a win anywhere else
            # on this site.
            "won_count": sum(1 for m in gs if m["corners_for"] > m["corners_against"]),
            "lost_count": sum(1 for m in gs if m["corners_for"] < m["corners_against"]),
        })
    return rows


def _best(rows, key, want=max):
    """The extreme row by `key`, ignoring rows where it is missing."""
    usable = [r for r in rows if r.get(key) is not None]
    return want(usable, key=lambda r: r[key]) if usable else None


def highest_floor(rows):
    """The team whose WORST game is the best worst game on the site.

    A DIFFERENT CLAIM FROM "HIGHEST AVERAGE", and a more interesting one. An average of 8
    can be four quiet nights and four storms; a floor of 5 across ten games means they
    have not had a quiet night at all.

    Measured over the fixed window — see `_team_rows`. Ties break towards the team with
    the longer record, because two sides with the same floor over the same ten games are
    not equally impressive if one of them has twenty on the books.
    """
    usable = [r for r in rows if r.get("floor") is not None]
    return max(usable, key=lambda r: (r["floor"], r["games"])) if usable else None


def lowest_ceiling(rows):
    """The opposite, and the one nobody expects to exist: a team whose BEST game in the
    window is still a low count. "Have not won more than 4 corners in a game in ten" is a
    fact of the same kind as a streak and points the other way, which is the variance."""
    usable = [r for r in rows if r.get("ceiling") is not None]
    return min(usable, key=lambda r: (r["ceiling"], -r["games"])) if usable else None


def widest_venue_gap(rows):
    """The biggest difference between what a side wins at home and what it wins away.

    SIGNED, AND BOTH DIRECTIONS COUNT. Teams that travel better than they play at home are
    rarer and therefore the better post, so this takes the largest gap either way and says
    which way it runs rather than assuming home is the big end.
    """
    usable = [r for r in rows if r.get("home_avg") is not None and r.get("away_avg") is not None]
    if not usable:
        return None
    best = max(usable, key=lambda r: abs(r["home_avg"] - r["away_avg"]))
    gap = round(best["home_avg"] - best["away_avg"], 2)
    return {**best, "gap": abs(gap), "stronger": "home" if gap > 0 else "away"}


def never_outcornered(rows):
    """A team that has finished with more corners than its opponent in EVERY game.

    The longest such record wins, because the claim is only as good as the run behind it —
    12 from 12 is a story and 10 from 10 is the same story told smaller. Ties go to the
    bigger corner average, which is the tie-break that picks the more extreme team rather
    than whichever the database happened to return first.
    """
    perfect = [r for r in rows if r["lost_count"] == 0 and r["won_count"] == r["games"]]
    if not perfect:
        return None
    return max(perfect, key=lambda r: (r["games"], r["for_avg"]))


def all_corners_no_goals(rows, top_fraction=0.15):
    """The futility record: plenty of corners, nothing to show for it.

    SELECTED IN TWO STEPS ON PURPOSE. A straight ratio of corners to goals would be won by
    whichever team happened to be goalless, however few corners it took — the denominator
    does the work and the headline number becomes meaningless. So this first restricts to
    teams in the top `top_fraction` for corners won, and only then takes the lowest goals
    inside that group. The claim is then "among the biggest corner-winners here, these
    score the least", which is what the sentence actually says.
    """
    usable = [r for r in rows if r.get("goals_avg") is not None and r.get("for_avg") is not None]
    if len(usable) < 20:
        return None
    ranked = sorted(usable, key=lambda r: r["for_avg"], reverse=True)
    cut = max(3, int(len(ranked) * top_fraction))
    pool = ranked[:cut]
    best = min(pool, key=lambda r: r["goals_avg"])
    return {**best, "pool": len(pool), "of": len(usable)}


def leakiest(rows):
    """Most corners conceded per game. The plainest record here, kept because it is the
    one a reader can picture instantly and it names the opposite kind of team to
    everything else above."""
    return _best(rows, "against_avg", max)


# ---------------------------------------------------------------------------
# League against league
# ---------------------------------------------------------------------------

def league_table(teams, leagues, meta, min_games=MIN_LEAGUE_GAMES):
    """Corners per MATCH by competition, highest first.

    PER MATCH, NOT PER TEAM-GAME, and the difference is a factor of two in the headline.
    Each team's record holds `corners_for` and `corners_against`, so one team-game already
    contains the whole match's corner count; averaging (for + against) over team-games
    therefore gives the per-match total directly. Averaging `corners_for` alone would give
    a per-side figure, which is the same fact in units nobody quotes.
    """
    buckets = defaultdict(list)
    for t in teams:
        lid = t.get("league_id") or ""
        for m in games_of(t):
            cf, ca = m.get("corners_for"), m.get("corners_against")
            if cf is None or ca is None:
                continue
            buckets[lid].append(cf + ca)
    out = []
    for lid, totals in buckets.items():
        if len(totals) < min_games:
            continue
        info = (meta or {}).get(lid) or {}
        out.append({"league_id": lid,
                    "league": (leagues or {}).get(lid) or info.get("name") or lid,
                    "country": info.get("country") or "", "tier": info.get("tier"),
                    "per_match": _avg(totals), "team_games": len(totals)})
    out.sort(key=lambda r: r["per_match"], reverse=True)
    return out


def league_extremes(table):
    """The top and bottom of that table, which is the post.

    The middle of a 28-row table is not interesting and does not fit in a tweet. The gap
    between the ends is: two professional leagues playing the same sport three corners a
    game apart is the kind of number people argue about, and arguing is the point.
    """
    if len(table) < 2:
        return None
    top, bottom = table[0], table[-1]
    return {"top": top, "bottom": bottom,
            "gap": round(top["per_match"] - bottom["per_match"], 2),
            "leagues": len(table)}


def punching_up(rows, table, min_games=PUNCH_MIN_GAMES):
    """A lower-division side that wins more corners than anyone in a top-flight league.

    THE BEST HOOK IN THE FILE, and the one the site is uniquely able to make: nowhere else
    is a League Two team's corner record sitting in the same table as Serie A's. It reads
    as a joke until the numbers are attached, which is exactly the shape of thing that
    gets read and argued with.

    HOW THE OPPONENT LEAGUE IS CHOSEN. Not "any league it beats" — that would pick
    whichever top flight happens to be weakest and the post would be about an obscure
    league nobody has heard of, which wastes the joke. It takes the BEST top-flight league
    it can still top, measured by that league's own leader, so the comparison lands on the
    strongest name available and the margin stays real.
    """
    tier1_ids = {r["league_id"] for r in table if r.get("tier") == 1}
    # BOTH SIDES OF THE COMPARISON CLEAR THE STIFFER BAR, not just the challenger. A
    # top-flight "leader" with twelve games on record is as thin a number as the one
    # beating it, and the claim is about which is genuinely higher.
    deep = [r for r in rows if (r.get("games") or 0) >= min_games]
    lower = [r for r in deep if (r.get("tier") or 0) >= 2 and r.get("for_avg") is not None]
    if not lower or not tier1_ids:
        return None
    # The leader of each top flight, by corners won per game.
    leaders = {}
    for r in deep:
        if r["league_id"] not in tier1_ids or r.get("for_avg") is None:
            continue
        cur = leaders.get(r["league_id"])
        if cur is None or r["for_avg"] > cur["for_avg"]:
            leaders[r["league_id"]] = r
    if not leaders:
        return None
    best = max(lower, key=lambda r: r["for_avg"])
    beaten = [lead for lead in leaders.values() if lead["for_avg"] < best["for_avg"]]
    if not beaten:
        return None
    # The strongest league it still tops: the one whose own leader is highest.
    target = max(beaten, key=lambda r: r["for_avg"])
    return {"team": best, "beats": target, "beaten_leagues": len(beaten),
            "of_top_flights": len(leaders)}


# ---------------------------------------------------------------------------
# The survey
# ---------------------------------------------------------------------------

#: Findings whose record is one match. Kept together because they can collide — see
#: `_match_records` — and the de-duplication below needs to know which these are.
MATCH_FINDINGS = ("biggest_rout", "biggest_haul", "wildest_game")


def _same_game(a, b):
    """Two records describing one match. Compared on team + opponent + date rather than a
    fixture id, because these come from a team's own match list and carry no id."""
    if not a or not b:
        return False
    return (a.get("team"), a.get("opponent"), a.get("date")) == \
           (b.get("team"), b.get("opponent"), b.get("date"))


def survey(teams, leagues=None, meta=None, min_games=MIN_GAMES):
    """Every finding, in one walk of the collection.

    Returns findings that are each either a record or None. NONE IS A REAL ANSWER and the
    caller must treat it as one: early in a season almost nothing clears MIN_GAMES, and a
    thin pool that still produced a confident superlative would be the dishonest outcome.
    The wording module drops a missing finding rather than relaxing anything.

    `pool` is what every claim is bounded by — see rule 3. A post that says "of the 548
    teams on this site" is checkable; one that says "in Europe" is not.
    """
    teams = list(teams or [])
    rout, haul, wildest = _match_records(teams, leagues, meta)
    rows = _team_rows(teams, leagues, meta, min_games)
    table = league_table(teams, leagues, meta)

    findings = {
        "biggest_rout": rout,
        "biggest_haul": haul,
        "wildest_game": wildest,
        "highest_floor": highest_floor(rows),
        "lowest_ceiling": lowest_ceiling(rows),
        "widest_venue_gap": widest_venue_gap(rows),
        "never_outcornered": never_outcornered(rows),
        "all_corners_no_goals": all_corners_no_goals(rows),
        "leakiest": leakiest(rows),
        "league_extremes": league_extremes(table),
        "punching_up": punching_up(rows, table),
    }

    # ONE MATCH, ONE FINDING. The biggest rout is very often also the biggest haul, and
    # offering both would be one fact wearing two headings — the padding this file was
    # written to remove. The rout keeps it when they collide, because a margin is the more
    # surprising half: 15 corners is a good night, 15 against 1 is a siege.
    if _same_game(findings["biggest_rout"], findings["biggest_haul"]):
        findings["biggest_haul"] = None
    for name in ("biggest_rout", "biggest_haul"):
        if _same_game(findings["wildest_game"], findings.get(name)):
            findings["wildest_game"] = None
            break

    return {
        "pool": {
            "teams": len(rows),
            "teams_seen": len(teams),
            "games": sum(len(games_of(t)) for t in teams),
            "leagues": len(table),
            "min_games": min_games,
        },
        "league_table": table,
        "findings": findings,
    }
