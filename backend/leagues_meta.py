"""The league list, in ONE place.

This used to live in `sync_real.py` with a hand-copied set of the same ids in
`server.py` as `MANAGED_LEAGUE_IDS`. That pairing was a trap: boot-time cleanup deletes
any league not in the server's set, so adding a league to the sync alone meant its data
was wiped on every restart — silently, and only visible as "that league never appears".

Kept free of imports and env vars on purpose. `sync_real.py` reads API_FOOTBALL_KEY at
import time, so `server.py` cannot import it; both can import this.
"""

LEAGUE_META = {
    "eng-pl":  {"api": 39,  "name": "Premier League",  "country": "England"},
    "eng-ch":  {"api": 40,  "name": "Championship",     "country": "England"},
    "eng-l1":  {"api": 41,  "name": "League One",       "country": "England"},
    "eng-l2":  {"api": 42,  "name": "League Two",       "country": "England"},
    "eng-nl":  {"api": 43,  "name": "National League",  "country": "England"},
    "aus-al":  {"api": 188, "name": "A-League",         "country": "Australia"},
    "nor-el":  {"api": 103, "name": "Eliteserien",      "country": "Norway"},
    # Norway's tiers are confusingly named: the SECOND level is called "1. divisjon"
    # (sponsored name OBOS-ligaen), and "2. divisjon" is the THIRD level. Both are here.
    "nor-d1":  {"api": 104, "name": "1. divisjon (OBOS-ligaen)", "country": "Norway"},
    "nor-d2":  {"api": 105, "name": "2. divisjon",      "country": "Norway"},
    "ned-ere": {"api": 88,  "name": "Eredivisie",       "country": "Netherlands"},
    "ned-ed":  {"api": 89,  "name": "Eerste Divisie",   "country": "Netherlands"},
    "bra-sa":  {"api": 71,  "name": "Série A",          "country": "Brazil"},
    "bra-sb":  {"api": 72,  "name": "Série B",          "country": "Brazil"},
    "ita-sa":  {"api": 135, "name": "Serie A",          "country": "Italy"},
    "fra-l1":  {"api": 61,  "name": "Ligue 1",          "country": "France"},
    "esp-ll":  {"api": 140, "name": "La Liga",          "country": "Spain"},
    "ger-bl":  {"api": 78,  "name": "Bundesliga",       "country": "Germany"},
    "ger-bl2": {"api": 79,  "name": "2. Bundesliga",    "country": "Germany"},
    "por-pl":  {"api": 94,  "name": "Primeira Liga",    "country": "Portugal"},
    "bel-pl":  {"api": 144, "name": "Jupiler Pro League","country": "Belgium"},
    "sco-pl":  {"api": 179, "name": "Premiership",      "country": "Scotland"},
    "tur-sl":  {"api": 203, "name": "Süper Lig",        "country": "Turkey"},
    "usa-ml":  {"api": 253, "name": "MLS",              "country": "USA"},
    "den-sl":  {"api": 119, "name": "Superliga",        "country": "Denmark"},
    "sui-sl":  {"api": 207, "name": "Super League",     "country": "Switzerland"},
    "aut-bl":  {"api": 218, "name": "Bundesliga",       "country": "Austria"},
    "gre-sl":  {"api": 197, "name": "Super League",     "country": "Greece"},
    "jpn-j1":  {"api": 98,  "name": "J1 League",        "country": "Japan"},
    "arg-lp":  {"api": 128, "name": "Liga Profesional", "country": "Argentina"},
}

# Leagues the app owns. Anything else in the DB is a leftover and gets cleaned up on
# boot — which is exactly why this is derived rather than typed out a second time.
MANAGED_LEAGUE_IDS = set(LEAGUE_META)
