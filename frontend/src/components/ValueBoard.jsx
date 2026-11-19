import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BadgePercent, ArrowRight, Info, ChevronDown } from "lucide-react";
import { api, tierMeta } from "@/lib/api";
import PreviewWall from "@/components/PreviewWall";
import { withFlag } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";
import { priceFreshness } from "@/lib/priceAge";
import TierBadge from "@/components/TierBadge";
import BookOdds from "@/components/BookOdds";
import CopyAngle from "@/components/CopyAngle";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import CopyDay from "@/components/CopyDay";
import { dayOptions, boardParams } from "@/lib/valueQuery";

// Everywhere you have found an edge, on one screen.
//
// The fixture page is where prices go in, one game at a time, and that is also where
// the answer stayed — you could only see what you had found by revisiting each fixture
// and remembering which ones you had done. This collects them: one row per game, the
// best line on it, ranked.
//
// ONE ROW PER GAME, not one per line. A fixture whose whole ladder is priced over the
// model would otherwise contribute six rows and push five other games off the screen,
// and those six are not six bets — you are taking one. The runners-up fold in behind the
// row instead.
//
// AND EVERY PRICE APPEARS, even the ones that cannot become a bet. The server now sends
// a row for each price stored, carrying a `status` and a plain-English `note` when
// something is wrong with it — the game kicked off, the fixture id no longer exists, the
// stored keys match no market. Those land in "Also priced" underneath rather than being
// dropped. The board was silently discarding them for a week, and an empty screen with
// six possible causes is not a bug report anyone can act on.

// BOTH FILTERS DEFAULT TO SHOWING EVERYTHING, and that is the whole lesson of this
// screen. It shipped defaulting to "next 7 days" AND "only lines with a positive edge",
// and a bookmaker's margin means most prices you type in sit BELOW fair — so the normal
// result of pasting a card of real odds was an empty board. Nothing was broken, and
// there was no way to tell that from the outside.
//
// A board whose job is "show me what I have priced" must not open by hiding most of it.
// Narrowing is a decision the reader makes once they can see what they are narrowing.
//
// THE LADDER GOES UP TO THE CAP, not just to 10%. It stopped at "10%+", which is the one
// band where the question "is this real?" starts to matter — so the only way to ask "show
// me just the big ones so I can check them" was to read the whole board and squint.
//
// The steps are 5s to 30 and then coarse, because that is where the meaning changes
// rather than where the arithmetic does: inside 30% an edge is an edge, past it the row
// is a job to do. 100%+ is not a filter anybody bets off — it is the shortlist of prices
// to go and fix, and it is on the ladder for that.
const FLOORS = [
  { v: "-100", l: "Everything I've priced" },
  { v: "0", l: "Positive edge only" },
  { v: "2", l: "2%+" },
  { v: "5", l: "5%+" },
  { v: "10", l: "10%+" },
  { v: "15", l: "15%+" },
  { v: "20", l: "20%+" },
  { v: "25", l: "25%+" },
  { v: "30", l: "30%+ — check these" },
  { v: "50", l: "50%+ — probably wrong" },
  { v: "100", l: "100%+ — broken prices" },
];

// WHAT THE SERVER'S VERDICT LOOKS LIKE. The band is computed in value_board so that this
// screen, the Telegram card and the spreadsheet cannot disagree about which edges to
// believe; all this does is colour it.
//
// `credible` gets no badge at all. Marking the normal case marks every row, and a board
// where everything carries a label has said nothing.
const CREDIBILITY = {
  stretch: { label: "big edge", cls: "text-amber-400 border-amber-400/40" },
  outlier: { label: "one book", cls: "text-amber-400 border-amber-400/40" },
  implausible: { label: "check the line", cls: "text-red-400 border-red-400/40" },
};

function Line({ m, muted = false }) {
  const t = m.tier ? tierMeta[m.tier] : null;
  const cred = CREDIBILITY[m.credibility] || null;
  return (
    <>
      <span className={muted ? "text-muted-foreground" : "text-foreground"}>{m.label}</span>
      <span className="text-muted-foreground"> @ </span>
      {/* THE BEST PRICE, WITH EVERY OTHER BOOK BEHIND IT. One number and one book name
          answers "can I take this" and not "is this a market, or one book out on its
          own" — and the second question is what decides whether an edge is believable.
          Falls back to plain text on rows stored before the feed kept every book. */}
      <BookOdds m={m} muted={muted} />
      <span className="text-muted-foreground/60 text-[10px]"> (fair {m.fair_odds?.toFixed(2)})</span>
      {/* THE EV LOSES ITS COLOUR ONCE IT STOPS MEANING WHAT IT SAYS. tierMeta paints
          anything over 5% as a strong edge, so a +240% misprice rendered in the same
          confident green as a +6% one. A flagged row prints the number in the flag's
          colour instead — the figure is still there to read, it just stops recommending
          itself. */}
      <span className={`ml-1.5 font-semibold ${
        cred ? cred.cls.split(" ")[0] : t ? t.text : "text-muted-foreground"}`}>
        {m.ev > 0 ? "+" : ""}{m.ev?.toFixed(1)}%
      </span>
      {cred && (
        <span data-testid="value-credibility" data-band={m.credibility}
          className={`ml-1.5 align-middle rounded border px-1 py-px text-[9px] uppercase
            tracking-wide font-sans ${cred.cls}`}>
          {cred.label}
        </span>
      )}
    </>
  );
}

// One game. `muted` is the "Also priced" variant — same shape, dimmed, headed by the
// reason it cannot be backed rather than by a price age.
function Row({ r, muted = false, open, setOpen, navigate }) {
  const fresh = priceFreshness(r.priced_at);
  const alts = r.alternatives || [];
  const isOpen = !!open[r.fixture_id];
  const named = r.home_name || r.away_name;
  return (
    <div data-testid="value-row" data-status={r.status || "ok"}
      className={`px-3 py-2.5 sm:px-4 sm:py-3 hover:bg-white/5 transition-colors ${muted ? "opacity-70" : ""}`}>
      <div className="flex items-start gap-3 cursor-pointer"
        onClick={() => navigate(`/fixture/${r.fixture_id}`)}>
        <div className="min-w-0 flex-1">
          <p className="font-sans font-medium text-sm truncate">
            {named
              ? <>{r.home_name} <span className="text-muted-foreground font-normal">v</span> {r.away_name}</>
              // No fixture behind the price any more, so the id is all there is to show.
              : <span className="text-muted-foreground font-mono-data text-xs">{r.fixture_id}</span>}
          </p>
          {named && (
            <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-muted-foreground uppercase tracking-wider">
              <span className="truncate">{withFlag(r.league_id, r.league_name)}</span>
              <TierBadge tier={r.tier} country={r.league_name} />
              {r.date && <><span className="opacity-40">·</span>
                <span className="normal-case tracking-normal text-primary/80">{kickoffLabel(r.date)}</span></>}
            </div>
          )}
          {r.best ? (
            <p className="mt-1 font-mono-data text-xs"><Line m={r.best} muted={muted} /></p>
          ) : (
            <p className="mt-1 font-mono-data text-[11px] text-muted-foreground">
              {r.market_count} {r.market_count === 1 ? "price" : "prices"} stored, none of them priced up
            </p>
          )}
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0 mt-1" />
      </div>

      {/* The reason, in the reader's words. This is the whole point of the muted group:
          a row that says "already kicked off" is information, a row that never rendered
          is a mystery. */}
      {r.note && (
        <p className="mt-1.5 text-[11px] leading-snug text-amber-400/80" data-testid="value-note">{r.note}</p>
      )}

      {/* WHY THE BADGE IS THERE, AND WHICH THING TO GO AND LOOK AT. The two reasons an
          edge gets too big are opposite jobs — a wrong line stored here, or a projection
          the whole market disagrees with — and a badge alone cannot say which. The server
          works out which from how many books quoted the market and how far clear the top
          price is, and sends the sentence. */}
      {r.best?.credibility_note && (
        <p data-testid="value-credibility-note"
          className={`mt-1.5 text-[11px] leading-snug ${
            r.best.credibility === "implausible" ? "text-red-400/90" : "text-amber-400/80"}`}>
          {r.best.credibility_note}
        </p>
      )}

      <div className="mt-1.5 flex items-center gap-3 flex-wrap">
        <span className={`text-[10px] font-mono-data ${fresh.cls}`}
          title={fresh.note || "Price entered recently"}
          data-testid="value-price-age">
          price {fresh.label}
        </span>
        {/* Only on a backable row. A muted row is one that has already kicked off or
            cannot be priced, and a Copy button on it is an invitation to post a game
            that is half over.
            AND NOT ON A BROKEN PRICE, for the same reason one step further on. A row
            the server has called implausible is a price stored against the wrong line;
            a Copy button beside it is one tap between a misprice and a paying channel,
            and it is the biggest number on the board so it is the one most likely to be
            tapped. `stretch` and `outlier` keep theirs — those say go and check, not
            definitely wrong. */}
        {!muted && r.best?.credibility !== "implausible" && <CopyAngle row={r} />}
        {alts.length > 0 && (
          <button
            onClick={() => setOpen((o) => ({ ...o, [r.fixture_id]: !o[r.fixture_id] }))}
            data-testid="value-alts-btn"
            aria-expanded={isOpen}
            className="inline-flex items-center gap-1 text-[10px] text-primary hover:text-primary/80 transition-colors"
          >
            <ChevronDown className={`h-3 w-3 transition-transform duration-150 ${isOpen ? "rotate-180" : ""}`} />
            {r.other_count} other {r.other_count === 1 ? "line" : "lines"} on this game
          </button>
        )}
      </div>

      {fresh.note && <p className={`mt-1 text-[10px] leading-snug ${fresh.cls}`}>{fresh.note}</p>}

      {isOpen && (
        <div className="mt-1.5 pl-3 border-l border-border/60 space-y-1" data-testid="value-alternatives">
          {alts.map((m) => <p key={m.key} className="font-mono-data text-[11px]"><Line m={m} muted /></p>)}
          {r.other_count > alts.length && (
            <p className="text-[10px] text-muted-foreground">
              +{r.other_count - alts.length} more on the fixture page
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ValueBoard() {
  const navigate = useNavigate();
  // Built once per mount, not per render: the labels are relative ("Today") and a list
  // rebuilt on every keystroke would swap identities underneath the open select.
  const [whens] = useState(() => dayOptions());
  const [days, setDays] = useState("all");
  const [floor, setFloor] = useState("-100");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  // Set by the API when the server trimmed this board for a non-member.
  const [preview, setPreview] = useState(null);
  const [open, setOpen] = useState({});          // fixture_id -> alternatives shown

  useEffect(() => {
    setLoading(true);
    api.valueBoard(boardParams(days, floor))
      .then((d) => {
        setRows(Array.isArray(d) ? d : []);
        setPreview(d?.preview ? { total: d.total } : null);
      })
      .catch(() => { setRows([]); setPreview(null); })
      .finally(() => setLoading(false));
  }, [days, floor]);

  // Rows with no status are pre-split servers still in flight during a deploy; treat
  // them as backable rather than dropping them into the muted group.
  const live = rows.filter((r) => !r.status || r.status === "ok");
  const other = rows.filter((r) => r.status && r.status !== "ok");

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="value-board">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <BadgePercent className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Your Value Board</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">
            every game you've priced, best line first
          </span>
          {rows.length > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground ml-1" data-testid="value-count">
              {live.length > 0
                ? <>{live.length} {live.length === 1 ? "game" : "games"}
                    {other.length > 0 && <span className="opacity-60"> · {other.length} more priced</span>}</>
                : <>{other.length} priced</>}
            </span>
          )}
        </div>
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Select value={floor} onValueChange={setFloor}>
            <SelectTrigger data-testid="value-floor" className="w-[120px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {FLOORS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger data-testid="value-window" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {whens.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          {/* ONLY ON A DAY. A card headed "Saturday 21st November" built from "all
              upcoming" would carry next Wednesday's games into Saturday's post, and the
              heading would be the part that lied. */}
          <CopyDay when={days} floor={floor}
            label={whens.find((o) => o.v === days)?.l || ""} />
        </div>
      </div>

      {loading ? (
        <div className="px-4 py-12 text-center text-muted-foreground animate-pulse font-mono-data text-sm">
          Checking your prices against the model…
        </div>
      ) : rows.length === 0 ? (
        // Reached only when nothing at all is stored. Every other reason a game might
        // not show up now arrives as a row that says so, so this message can be blunt.
        <div className="px-4 py-12 text-center text-muted-foreground text-sm" data-testid="value-empty">
          <p>You haven't priced anything yet.</p>
          <p className="mt-1 text-xs max-w-md mx-auto leading-relaxed">
            Open a game, put the shop's odds in the{" "}
            <span className="text-foreground">Your price</span> column, and it appears here —
            with an edge if the model rates it above that price, and with a reason if it
            can't be priced at all.
          </p>
        </div>
      ) : (
        <>
          {live.length > 0 && (
            <div className="divide-y divide-border/50">
              {live.map((r) => <Row key={r.fixture_id} r={r} open={open} setOpen={setOpen} navigate={navigate} />)}
            </div>
          )}

          {live.length === 0 && (
            <div className="px-4 py-8 text-center text-muted-foreground text-sm" data-testid="value-none-live">
              <p>Nothing you've priced clears the filters right now.</p>
              <p className="mt-1 text-xs max-w-md mx-auto leading-relaxed">
                Every price you've entered is listed below with the reason. Widening the two
                filters above is usually the fix.
              </p>
            </div>
          )}

          {other.length > 0 && (
            <div data-testid="value-other">
              <div className="px-3 py-1.5 sm:px-4 border-t border-border bg-white/[0.02] text-[10px] uppercase tracking-wider text-muted-foreground">
                Also priced — {other.length} {other.length === 1 ? "game" : "games"} that can't be backed right now
              </div>
              <div className="divide-y divide-border/50">
                {other.map((r) => <Row key={r.fixture_id} r={r} muted open={open} setOpen={setOpen} navigate={navigate} />)}
              </div>
              {/* The tail of a flood. Leftovers with no timestamp clear themselves on the
                  next sync; a recent price outlives its fixture on purpose, so you keep
                  the record of a game you backed after it has been played. */}
              {other.some((r) => r.more_orphans) && (
                <p className="px-3 sm:px-4 py-2 text-[11px] text-muted-foreground border-t border-border/50">
                  + {other.find((r) => r.more_orphans).more_orphans} more prices with no fixture
                  behind them.
                </p>
              )}
            </div>
          )}
        </>
      )}

      {preview && <PreviewWall total={preview.total} shown={rows.length} noun="games" />}

      {/* THE SELECTION EFFECT, now acted on rather than only admitted to. This said "be
          most suspicious of the biggest number" and then sorted the biggest numbers to the
          top of the page, which left the warning as something to scroll past. The sort
          puts the believable rows first; this explains where the others went. */}
      <div className="px-3 py-2.5 border-t border-border text-[11px] text-muted-foreground leading-relaxed">
        <p className="flex items-start gap-2">
          <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            <span className="text-foreground">The biggest number is not the best bet.</span>{" "}
            Ranking by EV ranks by how far the model disagrees with the market, which
            catches real edges and the model's own worst errors in the same net. A corner
            market is quoted by thirty-odd books and arbitraged between them, so an edge
            past <span className="text-amber-400">30%</span> needs the market to have
            missed something, and past <span className="text-red-400">100%</span> the
            price is not a price. Those rows are still here — flagged, with what to go and
            check, and sorted below the ones worth backing. Use the filter to pull them up
            when you want to fix them.
          </span>
        </p>
      </div>
    </section>
  );
}
