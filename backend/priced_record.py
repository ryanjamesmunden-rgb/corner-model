"""Offline: every section's record, with units at the price you typed, at posting, and at
the close — the Results page's "By section" panel, printed.

Exists so the answer can be read from GitHub Actions (Run a harness -> priced_record)
without signing in to the site. Reads the database only: no API calls, no writes.

Run: python priced_record.py
"""
import asyncio

import server


def _u(block):
    if not block or block.get("units") is None:
        return f"{'—':>8} {'':>7} {block.get('priced', 0) if block else 0:>4}"
    return (f"{block['units']:+8.2f} {block['roi']:+6.1f}% {block['priced']:>4}")


async def run():
    boards = await server.board_records()
    print("EVERY SECTION, PRICED — one claim per fixture, settled rows only\n")
    print("Units are 1u flat at the fetched prices; 'typed' uses your own stake.")
    print("Each price column counts only the rows that HAVE that price (n).\n")
    head = (f"{'section':16} {'settled':>7} {'landed':>6} {'rate':>6}  "
            f"{'typed u':>8} {'roi':>7} {'n':>4}  {'@post u':>8} {'roi':>7} {'n':>4}  "
            f"{'@close u':>8} {'roi':>7} {'n':>4}  {'clv':>6}")
    print(head)
    print("-" * len(head))
    for b in boards:
        p = b.get("prices") or {}
        rate = f"{b['hit_rate']:.1f}%" if b.get("hit_rate") is not None else "—"
        clv = p.get("clv") or {}
        clv_s = f"{clv['mean']:+.1f}%" if clv.get("mean") is not None else "—"
        print(f"{b['label'][:16]:16} {b['settled']:>7} {b['landed']:>6} {rate:>6}  "
              f"{_u(p.get('price'))}  {_u(p.get('post_price'))}  "
              f"{_u(p.get('close_price'))}  {clv_s:>6}")
        if b.get("residual") is not None:
            print(f"{'':16} board said {b['mean_prob']}%, landed {b['hit_rate']}% "
                  f"-> {b['residual']:+.1f} pts")
    print("\nHOW TO READ IT. '@close' is what backing every claim at the last pre-match"
          "\nprice would have returned — the fairest single comparison between sections,"
          "\nbecause it prices them all the same way. 'clv' is how much better the price at"
          "\nposting was than the close; positive means the post beat the market.")
    print("\nPost prices only exist for claims made after this was deployed (Nov 2026)."
          "\nClose prices exist only where the closing capture ran on that fixture.")


if __name__ == "__main__":
    asyncio.run(run())
