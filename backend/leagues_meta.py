"""The league list, in ONE place.

This used to live in `sync_real.py` with a hand-copied set of the same ids in
`server.py` as `MANAGED_LEAGUE_IDS`. That pairing was a trap: boot-time cleanup deletes
any league not in the server's set, so adding a league to the sync alone meant its data
was wiped on every restart — silently, and only visible as "that league never appears".

Kept free of imports and env vars on purpose. `sync_real.py` reads API_FOOTBALL_KEY at
import time, so `server.py` cannot import it; both can import this.
"""

LEAGUE_META = {
    "eng-pl":  {"api": 39,  "name": "Premier League",  "country": "England", "tier": 1},
    "eng-ch":  {"api": 40,  "name": "Championship",     "country": "England", "tier": 2},
    "eng-l1":  {"api": 41,  "name": "League One",       "country": "England", "tier": 3},
    "eng-l2":  {"api": 42,  "name": "League Two",       "country": "England", "tier": 4},
    "eng-nl":  {"api": 43,  "name": "National League",  "country": "England", "tier": 5},
    "aus-al":  {"api": 188, "name": "A-League",         "country": "Australia", "tier": 1},
    "nor-el":  {"api": 103, "name": "Eliteserien",      "country": "Norway", "tier": 1},
    # Norway's tiers are confusingly named: the SECOND level is called "1. divisjon"
    # (sponsored name OBOS-ligaen), and "2. divisjon" is the THIRD level.
    # 104 is CONFIRMED by probe_leagues.py — the provider agrees it is Norway, and the
    # last four finished games carried Corner Kicks 4/4.
    "nor-d1":  {"api": 104, "name": "1. divisjon (OBOS-ligaen)", "country": "Norway", "tier": 2},
    # NO nor-d2 ENTRY ON PURPOSE. It was added as api 105 from memory and the probe came
    # back MISMATCH — 105 is not Norway's 2. divisjon. Rather than ship an id that would
    # sync some other competition under a Norwegian name, the league is out until the
    # probe's country listing names the real one. Run: Tools -> "List leagues by country".
    "ned-ere": {"api": 88,  "name": "Eredivisie",       "country": "Netherlands", "tier": 1},
    "ned-ed":  {"api": 89,  "name": "Eerste Divisie",   "country": "Netherlands", "tier": 2},
    "bra-sa":  {"api": 71,  "name": "Série A",          "country": "Brazil", "tier": 1},
    "bra-sb":  {"api": 72,  "name": "Série B",          "country": "Brazil", "tier": 2},
    "ita-sa":  {"api": 135, "name": "Serie A",          "country": "Italy", "tier": 1},
    "fra-l1":  {"api": 61,  "name": "Ligue 1",          "country": "France", "tier": 1},
    "esp-ll":  {"api": 140, "name": "La Liga",          "country": "Spain", "tier": 1},
    "ger-bl":  {"api": 78,  "name": "Bundesliga",       "country": "Germany", "tier": 1},
    "ger-bl2": {"api": 79,  "name": "2. Bundesliga",    "country": "Germany", "tier": 2},
    "por-pl":  {"api": 94,  "name": "Primeira Liga",    "country": "Portugal", "tier": 1},
    "bel-pl":  {"api": 144, "name": "Jupiler Pro League","country": "Belgium", "tier": 1},
    "sco-pl":  {"api": 179, "name": "Premiership",      "country": "Scotland", "tier": 1},
    "tur-sl":  {"api": 203, "name": "Süper Lig",        "country": "Turkey", "tier": 1},
    "usa-ml":  {"api": 253, "name": "MLS",              "country": "USA", "tier": 1},
    "den-sl":  {"api": 119, "name": "Superliga",        "country": "Denmark", "tier": 1},
    "sui-sl":  {"api": 207, "name": "Super League",     "country": "Switzerland", "tier": 1},
    "aut-bl":  {"api": 218, "name": "Bundesliga",       "country": "Austria", "tier": 1},
    "gre-sl":  {"api": 197, "name": "Super League",     "country": "Greece", "tier": 1},
    "jpn-j1":  {"api": 98,  "name": "J1 League",        "country": "Japan", "tier": 1},
    "arg-lp":  {"api": 128, "name": "Liga Profesional", "country": "Argentina", "tier": 1},
}

# Leagues the app owns. Anything else in the DB is a leftover and gets cleaned up on
# boot — which is exactly why this is derived rather than typed out a second time.
# TIER is the level within its own COUNTRY: 1 = top flight, 2 = second tier, and so on.
#
# It exists because this app ranks teams ACROSS leagues — the homepage board sorts every
# side in the database by corners won, so a National League team sits directly above a
# Premier League one with nothing to tell them apart. Six corners a game is not the same
# achievement in the fifth tier as in the first, and the board could not say so.
#
# WHAT IT IS NOT: a strength score comparable between countries. England's Championship
# is a stronger league than several of the top flights here, so tier 2 does not mean
# "weaker than" any tier 1 elsewhere. It answers "what level is this, at home?" and
# nothing more. Anything claiming to compare a Danish first tier with a Brazilian one
# needs data this app does not have (coefficients, squad values), and inventing it from
# corner counts would be a number with a confident face and no evidence behind it.

MANAGED_LEAGUE_IDS = set(LEAGUE_META)
