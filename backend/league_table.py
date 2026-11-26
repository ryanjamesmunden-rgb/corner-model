"""Where each side sits in its league, worked out from the results already on file.

WHY THIS EXISTS. A corner line on its own says nothing about who is likely to be on the
ball. Bolton 6+ at home to West Brom (25 Nov 2026) was staked as if Bolton were the
stronger side; West Brom had been in the Championship far longer and sat above them, and
Bolton won one corner. The table position is the quickest check against that mistake, so
it goes on the fixture page next to the game-state numbers.

NO NEW API CALL. db.fixture_stats already holds every league fixture the sync has priced,
with both scores and the provider's season, so the table is rebuilt from that. The cost of
not calling /standings is coverage: a game the provider never gave corner stats for was
never cached, so it is missing here. `played` travels with every row so a side shown on
14 games when it has played 16 is visible as exactly that, not silently wrong.

Pure functions: no database, no HTTP, no imports from server.
"""
from typing import Dict, Iterable, List, Optional


def _scored(doc: dict) -> bool:
    return (doc.get("home_id") is not None and doc.get("away_id") is not None
            and isinstance(doc.get("home_goals"), int)
            and isinstance(doc.get("away_goals"), int))


def build_table(docs: Iterable[dict]) -> List[dict]:
    """Every side's league row, best first: points, then goal difference, then goals scored.

    `docs` are fixture_stats documents for ONE league and ONE season. Games without both
    scores are skipped rather than counted as 0-0, which would hand out a point for a match
    nobody has the result of."""
    rows: Dict[int, dict] = {}

    def row(tid):
        if tid not in rows:
            rows[tid] = {"team_id": tid, "played": 0, "won": 0, "drawn": 0, "lost": 0,
                         "gf": 0, "ga": 0}
        return rows[tid]

    seen = set()
    for d in docs or []:
        if not _scored(d):
            continue
        key = d.get("_id")
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        hg, ag = d["home_goals"], d["away_goals"]
        for tid, f, a in ((d["home_id"], hg, ag), (d["away_id"], ag, hg)):
            r = row(tid)
            r["played"] += 1
            r["gf"] += f
            r["ga"] += a
            if f > a:
                r["won"] += 1
            elif f == a:
                r["drawn"] += 1
            else:
                r["lost"] += 1

    out = []
    for r in rows.values():
        r["gd"] = r["gf"] - r["ga"]
        r["points"] = 3 * r["won"] + r["drawn"]
        out.append(r)
    out.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], str(r["team_id"])))
    for i, r in enumerate(out):
        r["position"] = i + 1
    return out


def position_of(table: List[dict], team_id) -> Optional[dict]:
    """One side's row with the size of the table it sits in, or None when it is not on it.

    None, not position 0, for a side with no scored game this season — a promoted side in
    its first week, or a synthesised fixture whose id is a string — so the page can say
    nothing rather than print a rank nobody earned."""
    if team_id is None:
        return None
    for r in table or []:
        if r["team_id"] == team_id:
            return {**r, "of": len(table)}
    return None
