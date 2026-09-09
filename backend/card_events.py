"""Cards: who went down to ten, and when.

WHY THIS EXISTS. A corner count is decided by who has to chase, and a sending-off is the
bluntest way that changes: ten men drop deep, defend the box and concede corners, while
the side with the extra man camps in the final third. It is the one big in-play swing the
site could describe but never measure — the fixture page carried a red-card note with no
number on it and said so.

WHERE IT COMES FROM. `/fixtures/events` — the SAME response the goal backfill already
fetches, which carries cards with minutes alongside goals. So the minute is free on any
fixture being fetched anyway; only catching up history costs a call.

A SECOND YELLOW IS A RED. The provider reports it inconsistently: sometimes
detail "Second Yellow card", sometimes a plain "Yellow Card" on a player who already had
one. The first form is caught here by name; the second is caught by counting a player's
yellows and treating the second as a dismissal. Missing that would undercount sendings-off
in exactly the matches most likely to have one.

Pure functions only — no API, no DB — so this is testable without either.
"""
from typing import List, Optional

RED = "red"
SECOND_YELLOW = "second_yellow"
YELLOW = "yellow"
# Both of these mean a player has left the pitch.
OFF = (RED, SECOND_YELLOW)


def _kind(detail: str) -> Optional[str]:
    """Which sort of card an event's `detail` describes, or None if it is not a card."""
    d = str(detail or "").strip().lower()
    if "second yellow" in d:
        return SECOND_YELLOW
    if "red" in d:
        return RED
    if "yellow" in d:
        return YELLOW
    return None


def parse_card_events(events, home_id, away_id) -> List[dict]:
    """`/fixtures/events` -> the cards, sorted, as {minute, side, kind, player}.

    A player's SECOND yellow is upgraded to a sending-off even when the provider labels it
    as an ordinary yellow, because that is what actually happened on the pitch."""
    cards = []
    seen_yellow = set()
    raw = []
    for e in events or []:
        if str(e.get("type", "")).strip().lower() != "card":
            continue
        kind = _kind(e.get("detail"))
        if kind is None:
            continue
        tid = ((e.get("team") or {}).get("id"))
        if tid not in (home_id, away_id):
            continue
        t = e.get("time") or {}
        minute = t.get("elapsed")
        if minute is None:
            continue
        raw.append({
            "minute": int(minute), "extra": t.get("extra") or 0,
            "side": "home" if tid == home_id else "away",
            "kind": kind,
            "player": ((e.get("player") or {}).get("name")),
        })

    raw.sort(key=lambda c: (c["minute"], c["extra"]))
    for c in raw:
        if c["kind"] == YELLOW:
            key = (c["side"], c["player"])
            # An unnamed player cannot be tracked across events, so a second yellow for
            # one is left as a yellow rather than guessed at.
            if c["player"] and key in seen_yellow:
                c = {**c, "kind": SECOND_YELLOW}
            elif c["player"]:
                seen_yellow.add(key)
        cards.append(c)
    return cards


def card_summary(cards: List[dict]) -> dict:
    """Everything derived from one match's cards, ready to store per fixture."""
    out = {"cards": cards}
    for side in ("home", "away"):
        mine = [c for c in cards if c["side"] == side]
        offs = [c for c in mine if c["kind"] in OFF]
        out[f"{side}_reds"] = len(offs)
        out[f"{side}_yellows"] = sum(1 for c in mine if c["kind"] == YELLOW)
        out[f"{side}_first_red_min"] = offs[0]["minute"] if offs else None
    return out


def team_card_sample(summary: dict, side: str) -> dict:
    """The per-team-per-match keys stored on team.real_matches.

    Both directions are kept. A team's OWN red is the risk to a corners-over on them; the
    OPPONENT's is the gift, and it is the half a one-sided record would lose."""
    other = "away" if side == "home" else "home"
    return {
        "red_cards_for": summary[f"{side}_reds"],
        "red_cards_against": summary[f"{other}_reds"],
        "yellow_cards_for": summary[f"{side}_yellows"],
        "yellow_cards_against": summary[f"{other}_yellows"],
        "first_red_min_for": summary[f"{side}_first_red_min"],
        "first_red_min_against": summary[f"{other}_first_red_min"],
    }
