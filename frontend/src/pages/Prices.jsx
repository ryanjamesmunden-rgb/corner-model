import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardPaste, Loader2, Check, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { parseBulk } from "@/lib/pastePrices";
import MembersOnly from "@/components/MembersOnly";
import { flagBullet } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";

// PRICE A WHOLE WEEKEND IN ONE PASTE.
//
// The per-fixture box works and has for a while, but it prices one game at a time, which
// means eight page loads for a weekend. Prices that are annoying to enter do not get
// entered — and with no prices the model has nothing to measure value against, so every
// pick falls back to form and the whole value half of the site is dark.
//
// NOTHING IS GUESSED, which is the part that matters more than the convenience. A line
// that cannot be matched to a game is listed back rather than attached to whatever came
// last. A price silently landing on the wrong fixture produces a board that looks priced,
// shows an edge, and is about a different match — worse than no price at all, because it
// is indistinguishable from a real one.
//
// See lib/pastePrices for the routing, which is where the tests are.
// THE WALL IS ON THE PAGE, NOT ONLY ON THE LINK. Hiding the nav item for non-members
// hides the door; it does not lock it, and the URL is four words long. The server refuses
// the write either way — this is so the refusal arrives before a paste rather than after
// one, and so it explains itself instead of reading as a bug.
export default function Prices() {
  return (
    <MembersOnly
      title="Pasting prices is a members' feature"
      blurb="Prices entered here are what the model measures value against — they drive the
             value board, and they decide which game the daily post goes out on. That is
             why writing them is not open.">
      <PricesBoard />
    </MembersOnly>
  );
}

function PricesBoard() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  // The streak board is the right source: these are the games with something live running
  // into them, which is exactly the set worth pricing. Ten days, because a Wednesday paste
  // has to reach the following weekend.
  const { data, isLoading } = useQuery({
    queryKey: ["prices-fixtures"],
    queryFn: () => api.streaks({ league_id: "all", side: "overall", window: 5, min_hits: 5,
                                 min_line: 3, within_days: 10, direction: "over",
                                 subject: "team" }),
  });

  const fixtures = useMemo(() => {
    const seen = new Map();
    for (const r of (data || [])) {
      const nf = r.next_fixture;
      if (!nf?.fixture_id || seen.has(nf.fixture_id)) continue;
      seen.set(nf.fixture_id, {
        fixture_id: nf.fixture_id,
        home_name: nf.is_home ? r.name : nf.opponent,
        away_name: nf.is_home ? nf.opponent : r.name,
        league_id: r.league_id, date: nf.date,
      });
    }
    return [...seen.values()].sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [data]);

  const preview = useMemo(() => parseBulk(text, fixtures), [text, fixtures]);

  const save = async () => {
    if (!preview.entries.length) { toast.error("Nothing matched a game yet"); return; }
    setBusy(true);
    let ok = 0;
    const failed = [];
    let refused = null;
    for (const e of preview.entries) {
      try {
        // One call per fixture, deliberately sequential. A burst of parallel writes to a
        // sleeping free-tier backend is how half of them time out and the board ends up
        // half priced with no record of which half.
        await api.setOdds(e.fixture.fixture_id,
          Object.fromEntries(Object.entries(e.odds).map(([k, v]) => [k, Number(v)])));
        ok += 1;
      } catch (err) {
        // A REFUSAL IS NOT A FAILURE, and reporting it as one sends someone to retry a
        // thing that will never work. 401 and 402 mean the write was understood and
        // declined, and they need different answers — one is "sign in", the other is
        // "subscribe". Everything else really is worth trying again.
        const code = err?.response?.status;
        if (code === 401 || code === 402) { refused = code; break; }
        failed.push(`${e.fixture.home_name} v ${e.fixture.away_name}`);
      }
    }
    setBusy(false);
    setDone({ ok, failed, refused });
    if (refused) {
      toast.error(refused === 401 ? "Sign in to enter prices"
                                  : "Entering prices is a members' feature");
    } else if (failed.length) toast.error(`${ok} saved, ${failed.length} failed`);
    else { toast.success(`Priced ${ok} game${ok === 1 ? "" : "s"}`); setText(""); }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4" data-testid="prices-page">
      <div>
        <h1 className="font-head text-xl font-semibold">Paste prices</h1>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
          One paste, many games. A line naming both teams switches the game; the lines under
          it are its prices. Understands <span className="font-mono-data">Over 4.5 1.80</span>,{" "}
          <span className="font-mono-data">5+ 1.80</span> and{" "}
          <span className="font-mono-data">Total 10.5 1.90</span>.
          {" "}<span className="text-amber-400">Anything it cannot place is listed back, never guessed.</span>
        </p>
      </div>

      <textarea
        value={text} onChange={(e) => { setText(e.target.value); setDone(null); }}
        data-testid="prices-paste" rows={12}
        placeholder={"Club Brugge v Antwerp\nClub Brugge 5+ 1.40\nAntwerp 4+ 2.10\nTotal 10.5 1.90\n\nJuventus v Sassuolo\nJuventus 6+ 2.05"}
        className="w-full bg-[#121212] border border-border rounded p-3 text-sm font-mono-data
                   focus:outline-none focus:ring-2 focus:ring-primary" />

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={save} disabled={busy || !preview.entries.length}
          data-testid="prices-save"
          className="flex items-center gap-2 text-sm px-4 py-2 rounded bg-primary
                     text-primary-foreground font-semibold disabled:opacity-40">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardPaste className="h-4 w-4" />}
          {busy ? "Saving…" : `Save ${preview.entries.length || ""} game${preview.entries.length === 1 ? "" : "s"}`.trim()}
        </button>
        <span className="text-xs text-muted-foreground">
          {isLoading ? "loading fixtures…" : `${fixtures.length} games with a run into them`}
        </span>
      </div>

      {/* WHAT IT WILL DO, BEFORE IT DOES IT. Prices are the input to every EV on the site,
          so the one thing this must never be is a box that swallows a paste and reports a
          number. Every line is shown against the game it landed on. */}
      {preview.entries.length > 0 && (
        <div className="bg-card border border-border rounded-lg overflow-hidden"
          data-testid="prices-preview">
          <div className="px-4 py-2 border-b border-border text-xs text-muted-foreground">
            About to price {preview.entries.length} game{preview.entries.length === 1 ? "" : "s"}
          </div>
          {preview.entries.map((e) => (
            <div key={e.fixture.fixture_id} className="px-4 py-2 border-b border-border/50 last:border-0">
              <div className="text-sm">
                {flagBullet(e.fixture.league_id)} {e.fixture.home_name} v {e.fixture.away_name}
                <span className="text-muted-foreground text-xs ml-2">
                  {kickoffLabel(e.fixture.date)}
                </span>
              </div>
              <div className="text-[11px] font-mono-data text-muted-foreground mt-0.5">
                {Object.entries(e.odds)
                  .map(([k, v]) => `${k.replace(/_over_/, " ")} @ ${v}`).join("   ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {preview.unmatched.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3"
          data-testid="prices-unmatched">
          <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold mb-1">
            <AlertTriangle className="h-3.5 w-3.5" />
            {preview.unmatched.length} line{preview.unmatched.length === 1 ? "" : "s"} not placed
          </div>
          <p className="text-[11px] text-muted-foreground mb-2">
            Either no game was named above them, or the market is not one this fixture has.
            They are shown rather than dropped — a line that vanishes looks the same as one
            that saved.
          </p>
          <ul className="text-[11px] font-mono-data text-muted-foreground space-y-0.5">
            {preview.unmatched.slice(0, 12).map((u, i) => <li key={i}>{u}</li>)}
          </ul>
        </div>
      )}

      {done?.refused && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-xs
                        leading-relaxed" data-testid="prices-refused">
          <p className="text-amber-400 font-semibold mb-1">
            {done.refused === 401 ? "Sign in first" : "Members only"}
          </p>
          <p className="text-muted-foreground">
            Prices entered here drive the value board and decide which game the daily post
            goes out on, so they are not open to write.{" "}
            {done.refused === 401
              ? "Sign in at the top right, then paste again — nothing you typed is lost."
              : "Your paste is still here; subscribing turns the save on."}
          </p>
        </div>
      )}

      {done && !done.refused && (
        <div className="text-xs" data-testid="prices-done">
          <span className="text-emerald-400 inline-flex items-center gap-1">
            <Check className="h-3.5 w-3.5" /> {done.ok} saved
          </span>
          {done.failed.length > 0 && (
            <span className="text-red-400 ml-3">
              failed: {done.failed.join(", ")} — try those again
            </span>
          )}
        </div>
      )}
    </div>
  );
}
