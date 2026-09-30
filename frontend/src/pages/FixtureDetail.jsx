import { useState, useEffect, useCallback, Fragment } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, TrendingUp, TrendingDown, ClipboardPaste, Flame, Shield, MapPin, Swords, Eye,
  Lock, History, BarChart3, Video,
} from "lucide-react";
import StarButton from "@/components/StarButton";
import ShareButtons from "@/components/ShareButtons";
import PostPick from "@/components/PostPick";
import { fixtureStreakShare, mismatchShare } from "@/lib/shareText";
import StoryButton from "@/components/StoryButton";
import { renderFormStory, renderMismatchStory } from "@/lib/storyImage";
import { canRecord, extFor, recordStoryVideo } from "@/lib/storyVideo";
import { kickoffLabel } from "@/lib/kickoff";
import { fixtureStreaks, streakDetail, streakHeadline } from "@/lib/fixtureStreaks";
import { hasH2H, meetingRows, recordLine, summaryLine, unbeatenRows } from "@/lib/h2h";
import {
  SUBJECTS as CONSISTENCY_SUBJECTS, consistencyHeadline, consistencyRows, defaultLine,
  gameBars, hitsAt, lineWindow, valuesFor, windowsFor,
} from "@/lib/consistency";
import { claimLine, hasMismatch, headline as mismatchHeadline, mismatches } from "@/lib/mismatch";
import { useAuth } from "@/context/AuthContext";
import { canWritePrices } from "@/lib/locked";
import ProbabilityChart from "@/components/ProbabilityChart";
import { api, tierMeta, confMeta } from "@/lib/api";
import { isCrossLeague, transferNote } from "@/lib/cupRow";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

// Bands, not a gradient: a rate either reads as reliable, playable, thin or unlikely.
// Shared by the match-total table and the team-corner tables so the two cannot show the
// same number in different colours — the team tables previously had NO colour at all,
// which made a 78% line and a 22% line look equally worth reading.
//
// How reliable a rate is, is an ORDINAL question, so the top two bands are one hue at two
// intensities rather than two different colours. Cyan used to sit in the middle of this
// ladder, which spent the brand colour on a status and made "playable" look like a button.
// Amber marks where the evidence gets thin — what amber means everywhere else on the site
// — and the bottom band recedes entirely.
const band = (pct) =>
  pct >= 70 ? { text: "text-tone-strong-fg", bar: "bg-tone-strong", chip: "bg-tone-strong/20 border-tone-strong/45", label: "reliable" }
  : pct >= 50 ? { text: "text-tone-strong-fg/80", bar: "bg-tone-strong/60", chip: "bg-tone-strong/10 border-tone-strong/25", label: "playable" }
  : pct >= 30 ? { text: "text-tone-streak-fg", bar: "bg-tone-streak", chip: "bg-tone-streak/15 border-tone-streak/40", label: "thin" }
  : { text: "text-muted-foreground/60", bar: "bg-slate-600", chip: "border-border/60", label: "unlikely" };

const WINDOW_LABELS = { "3": "L3", "5": "L5", "10": "L10", "0": "Season" };

// The staking panel spans the whole table, and the table is wider than a phone — so left
// alone the "Back it" button sat off the right edge of the screen exactly like the trigger
// used to. Capping the width at the screen makes it wrap instead of overflow, and sticky
// then keeps it against the left edge however far the table underneath is scrolled.
const PANEL_CELL = "sticky left-0 max-w-[calc(100vw-2.5rem)] px-3 pb-2.5";

export default function FixtureDetail() {
  // `member` straight off the context rather than derived from `user`: the provider already
  // computes it, and two places deciding what "a member" means is how they come to disagree.
  const { member } = useAuth();
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [odds, setOdds] = useState({});
  const [paste, setPaste] = useState("");
  // Defaults to totals: it is the market at the top of the page and the one most
  // people are pricing. An unrecognised line lands here rather than nowhere.
  const [pasteTarget, setPasteTarget] = useState("total");
  const [flash, setFlash] = useState({});
  // Which market has its staking panel open, by key — ONE AT A TIME, and held here rather
  // than inside each row, because the panel is a sibling row and a row cannot render its
  // own sibling. Market keys are unique across both team tables, so one value covers them.
  const [backing, setBacking] = useState(null);

  const load = useCallback(() => {
    api.fixture(id).then((d) => {
      setData(d);
      const o = {};
      d.model.markets.forEach((m) => { if (m.book_odds) o[m.key] = String(m.book_odds); });
      setOdds(o);
    }).catch(() => toast.error("Failed to load fixture"));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const submitOdds = async (next) => {
    const payload = {};
    Object.entries(next).forEach(([k, v]) => { const n = parseFloat(v); if (n > 1) payload[k] = n; });
    try {
      const res = await api.setOdds(id, payload);
      setData((d) => ({ ...d, model: res.model }));
      const fl = {}; Object.keys(payload).forEach((k) => { fl[k] = true; });
      setFlash(fl); setTimeout(() => setFlash({}), 800);
      toast.success("EV recalculated");
    } catch (err) {
      // The same three-way split the bulk page makes. "Could not save" on a 402 reads as
      // a bug and gets retried; it is a decision, and it has an answer.
      const code = err?.response?.status;
      toast.error(code === 401 ? "Sign in to enter prices"
        : code === 402 ? "Entering prices is a members' feature"
        : "Could not save odds");
    }
  };

  const nameHit = (line, name) => {
    const toks = name.toLowerCase().split(/\s+/).filter((t) => t.length >= 4);
    return toks.some((t) => line.includes(t));
  };

  const handlePaste = () => {
    const homeName = fixture.home_name;
    const awayName = fixture.away_name;
    const lines = paste.split(/\n|;/).map((s) => s.trim()).filter(Boolean);
    const next = { ...odds };
    let matched = 0;
    lines.forEach((raw) => {
      const low = raw.toLowerCase();
      // route to a market group: explicit team name > "total" keyword > selected target
      let group = pasteTarget;
      if (nameHit(low, homeName)) group = "home";
      else if (nameHit(low, awayName)) group = "away";
      else if (/\btotal\b|\bmatch\b|\bgame\b/.test(low)) group = "total";
      const nums = raw.match(/\d+\.?\d*/g);
      if (!nums || nums.length < 2) return;
      let lineVal = parseFloat(nums[0]);
      const price = parseFloat(nums[nums.length - 1]);
      // "5+" or a whole number → N or more corners = Over (N-0.5)
      const isPlus = /\d+\s*\+/.test(raw) || Number.isInteger(lineVal);
      if (isPlus) lineVal = lineVal - 0.5;
      const key = `${group}_over_${lineVal}`;
      if (data.model.markets.some((m) => m.key === key) && price > 1) {
        next[key] = String(price); matched++;
      }
    });
    if (matched === 0) { toast.error('No matching lines. Try "Over 4.5 1.80" or "5+ 1.80"'); return; }
    setOdds(next); submitOdds(next); setPaste("");
    toast.success(`Parsed ${matched} line${matched > 1 ? "s" : ""}`);
  };

  if (!data) return <div className="py-20 text-center text-muted-foreground animate-pulse font-mono-data text-sm">Loading fixture…</div>;

  const { fixture, model, home_team, away_team } = data;
  const keyFactors = data.key_factors || {};
  // THE SERVER DECIDES THIS, NOT THE PAGE. `blurred` is set by _blur_model when the reader
  // is not a member, and the numbers it refers to are already gone from the payload — so
  // this only chooses how to DRAW an absence, never whether to reveal something. A
  // client-side check would be a lock with the values sitting in the network tab.
  const blurred = !!model.blurred;
  // WHO MAY TYPE A PRICE. The rule lives in lib/locked beside the other "what may this
  // reader see" decisions, where a test can pin it against the server's own gate — jest
  // here cannot render this page, so anything asserted about it has to live in a module.
  const canPrice = canWritePrices({ member });
  // Every market — totals included — now carries fair odds, your price and the EV
  // between them. See TotalCorners for why totals were the exception and no longer are.
  const groups = [
    { key: "home", label: `${fixture.home_name} Corners`, team: home_team, venue: true },
    { key: "away", label: `${fixture.away_name} Corners`, team: away_team, venue: false },
  ];

  return (
    <div className="space-y-2.5 sm:space-y-4" data-testid="fixture-detail-page">
      <button onClick={() => navigate(-1)} data-testid="back-btn" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors duration-150">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      {/* Header */}
      <div className="bg-card border border-border rounded-lg p-3.5 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
        <div className="flex-1">
          {/* The most natural place to save a game is the game's own page — this was the
              one surface the star was missing from, which is most of why it could not
              be found. */}
          <div className="flex items-start gap-2">
            <StarButton fixtureId={fixture.fixture_id} size="lg" />
            <h1 className="font-head text-2xl sm:text-3xl font-bold tracking-tight">
              {fixture.home_name} <span className="text-muted-foreground font-normal">vs</span> {fixture.away_name}
            </h1>
          </div>
          <p className="font-mono-data text-xs text-muted-foreground mt-1">
            {new Date(fixture.date).toLocaleString()}
            {fixture.round && fixture.round !== "Upcoming" && (
              <span data-testid="fixture-round" className="ml-2 text-primary/80">· {fixture.round}</span>
            )}
          </p>
        </div>
        {/* Wraps on a phone instead of running off the edge, and the confidence chip
            goes with them rather than being pushed onto its own line. */}
        <div className="flex flex-wrap gap-2 sm:gap-3">
          <Metric label="λ Home" value={model.lambdas.home.toFixed(2)} />
          <Metric label="λ Away" value={model.lambdas.away.toFixed(2)} />
          <Metric label="λ Total" value={model.lambdas.total.toFixed(2)} accent />
          <div className="flex flex-col items-center justify-center px-3 py-2 bg-secondary rounded-md">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Confidence</span>
            <span className={`text-xs px-2 py-0.5 rounded border ${confMeta[model.confidence.label]}`}>{model.confidence.label} · {model.confidence.score}</span>
          </div>
        </div>
      </div>

      {/* THE CAVEAT SITS ABOVE THE NUMBERS, not in a footnote under them.
          Everything below this line — the splits, the traits, the corner ladders, the
          priced markets — is each side's DOMESTIC form, and on a cross-league tie the two
          records were earned against different opposition. The page is otherwise
          indistinguishable from a league fixture, so a reader who scrolls past the bottom
          never learns it. Absent entirely on a domestic game, and on an all-English tie
          in Europe where both records really are comparable. */}
      {isCrossLeague(data.competition) && (
        <div data-testid="cup-transfer-note"
          className="bg-amber-500/10 border border-amber-500/25 rounded-lg px-3.5 py-2.5">
          <p className="text-xs text-amber-200/90 leading-relaxed">
            <span className="font-semibold">{data.competition?.name || "Cup tie"}.</span>{" "}
            {transferNote(data.competition)}
          </p>
        </div>
      )}

      {/* The headline answer, drawn. This leads the page on purpose: it is the one thing a
          visitor who has never used the site can read, and everything below is the detail
          behind it rather than the other way round. */}
      {/* THE CURVE IS THE MODEL, so it goes with the rest of its numbers. A reader can
          hold a ruler to a probability mass function and recover the percentages the
          columns below now withhold, which would make the lock decorative. What replaces
          it says so plainly rather than leaving a gap where the page's headline was. */}
      {blurred ? (
        <div className="bg-card border border-border rounded-lg px-4 py-5 text-center"
          data-testid="chart-locked">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Lock className="h-3.5 w-3.5" />
            <span className="text-sm">The projection curve is for members.</span>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
            Everything below is the record this game is built on — both sides' corner
            ladders, the runs going into it and the form splits. What a subscription adds is
            the model's own line: the probability, the fair price and the edge against yours.
          </p>
        </div>
      ) : (
        <ProbabilityChart distribution={model.distribution} lambdas={model.lambdas}
          markets={model.markets} leagueId={fixture.league_id} kickoff={fixture.date}
          homeName={fixture.home_name} awayName={fixture.away_name} />
      )}

      {/* Who is playing, in words. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
        <TeamRead name={fixture.home_name} profile={home_team.profile} where="home" />
        <TeamRead name={fixture.away_name} profile={away_team.profile} where="away" />
      </div>

      {/* THE RUN THAT BROUGHT THEM HERE. /streaks advertises it, and clicking the fixture
          used to lose it: this payload was already on the page and went only to the share
          button, so the one thing that made the reader click was the one thing the
          destination never said. The share button stays, inside the panel now — POST THE
          GAME, NOT THE BOARD, and the model's price stays on the site as ever. */}
      <RunningStreaks
        streaks={data.streaks || []}
        share={fixtureStreakShare({ fixture, streaks: data.streaks || [],
                                    form: data.form || [], leagueName: data.league_name })}
      />

      {/* THE MISMATCH: one side's corners-won record against the other's conceded record,
          at a line BOTH of them clear. The two streak boards each tell half of this and
          neither can say that those two sides are playing each other — which is the only
          version of it that is actionable. Renders on the fixtures where it is true and
          nowhere else; most games are not a mismatch. */}
      <Mismatch home={home_team} away={away_team} fixture={fixture}
                leagueName={data.league_name} />

      {/* WHAT THESE TWO HAVE DONE TO EACH OTHER BEFORE. Closed by default and one line
          wide when shut: it is context for the projection above, not the projection
          itself, and a fixture page that opens on nine rows of history buries the
          numbers somebody came for. */}
      <HeadToHead h2h={data.h2h} homeName={fixture.home_name} awayName={fixture.away_name} />

      {/* THE BULK ENTRY BOX. This parser was written, complete, and never rendered —
          `handlePaste` had no caller, so filling a ladder meant eight separate inputs
          and eight round trips. Prices arrive from a bookmaker as a block of text, so
          this takes them as a block: it reads a team name or the word "total" to route
          each line, understands both "Over 9.5 1.85" and "10+ 1.85", and prices every
          market on the page in one go. */}
      {/* WRITE CONTROL, SAME GATE. It posts to the same members-only endpoint as the
          inputs below, so showing it to a reader who cannot write is the same dead end
          with a bigger box. */}
      {canPrice && <PastePrices
        value={paste}
        onChange={setPaste}
        target={pasteTarget}
        onTarget={setPasteTarget}
        onSubmit={handlePaste}
        homeName={fixture.home_name}
        awayName={fixture.away_name}
      />}

      {/* TEAM CORNERS FIRST — this used to lead with the match total, and that was the
          wrong way round for the bet rather than for the layout. A team line needs ONE
          side to do what it has been doing; a match total needs both, and the second
          team is a whole extra way to be wrong that you are not being paid extra for.
          The page should open on the market with the fewer moving parts. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 sm:gap-4">
        {groups.map((g) => (
          <div key={g.key} className="bg-card border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-head font-semibold text-sm">{g.label}</h3>
            </div>
            {/* Wide on a phone: the card clips, so the table needs its own scroller. */}
            <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                  <th className="text-left font-medium px-3 py-2">Line</th>
                  {/* w-full on the BAR column. A six-column table in a wide card
                      distributes its slack evenly, which flung Line, Prob, Fair, Book
                      and EV to the far corners with a hand's width of nothing between
                      them. Letting the one elastic column swallow the extra space keeps
                      the numbers together and readable as a row. */}
                  <th className="text-left font-medium px-3 py-2 w-full"
                    title="How often this team ACTUALLY hit the line, in its games on this venue">Landed</th>
                  <th className="text-right font-medium px-3 py-2 whitespace-nowrap">Prob</th>
                  <th className="text-right font-medium px-3 py-2">Fair</th>
                  <th className="text-right font-medium px-3 py-2">Book</th>
                  <th className="text-right font-medium px-3 py-2">EV</th>
                  <th className="sticky right-0 bg-card px-2 py-2" />
                </tr>
              </thead>
              <tbody className="font-mono-data text-sm">
                {model.markets.filter((m) => m.group === g.key).map((m) => {
                  const t = m.tier ? tierMeta[m.tier] : null;
                  // Colour by what actually happened, not by the model's own probability —
                  // the same evidence the match-total table uses, on the same bands.
                  // Venue-filtered, because the market is for this team at this venue and
                  // the model prices it that way too.
                  const played = (g.team?.recent || []).filter((x) => x.home === g.venue);
                  const plus = Math.ceil(m.line ?? parseFloat(String(m.key).split("_").pop()));
                  const hit = played.filter((x) => (x.won ?? -1) >= plus).length;
                  const pct = played.length ? Math.round((hit / played.length) * 100) : null;
                  const c = band(pct ?? 0);
                  const dim = pct != null && pct < 30;
                  const backingThis = backing === m.key;
                  return (
                    <Fragment key={m.key}>
                    <tr data-testid={`market-row-${m.key}`}
                      className={`transition-colors ${backingThis ? "" : "border-b border-border/50"} ${flash[m.key] ? "flash-green" : ""} ${dim ? "opacity-60" : ""}`}>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${c.chip} ${c.text}`}
                          title={pct == null ? "no games on this venue yet" : `${c.label} — landed ${hit}/${played.length} on this venue`}>
                          {m.label}
                        </span>
                      </td>
                      <td className="px-3 py-2 w-full">
                        {pct == null ? <span className="text-muted-foreground text-xs">—</span> : (
                          <div className="flex items-center gap-2">
                            <span className={`${c.text} text-xs font-semibold w-9 shrink-0`}>{hit}/{played.length}</span>
                            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex-1 min-w-[28px] max-w-[150px]">
                              <div className={`h-full rounded-full ${c.bar}`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className={`${c.text} text-xs w-8 text-right`}>{pct}%</span>
                          </div>
                        )}
                      </td>
                      {/* m.prob.toFixed(1) was unguarded, and a blurred model has no
                          `prob` — so withholding it would have thrown here and taken the
                          whole fixture page down rather than hiding a column. */}
                      <td className="px-3 py-2 text-right text-muted-foreground">
                        {modelNum(m.prob, (v) => `${v.toFixed(1)}%`, blurred)}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">
                        {modelNum(m.fair_odds, (v) => v.toFixed(2), blurred)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {canPrice ? (
                          <input
                            data-testid={`odds-input-${m.key}`}
                            value={odds[m.key] || ""}
                            onChange={(e) => setOdds({ ...odds, [m.key]: e.target.value })}
                            onBlur={() => odds[m.key] && submitOdds(odds)}
                            onKeyDown={(e) => e.key === "Enter" && submitOdds(odds)}
                            placeholder="—"
                            className="w-16 bg-black border border-border rounded px-1.5 py-1 text-right text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                          />
                        ) : modelNum(m.book_odds, (v) => v.toFixed(2), blurred)}
                      </td>
                      <td className={`px-3 py-2 text-right font-semibold ${t ? t.text : "text-muted-foreground"}`}>
                        {modelNum(m.ev, (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`, blurred)}
                      </td>
                      {/* BACK IT, only where there is a price to back it AT. The server
                          refuses a bet on a market with no book odds, so offering the
                          button without them would be a button that always errors. */}
                      <td className="sticky right-0 bg-card px-2 py-2 text-right">
                        <BackButton market={m} open={backingThis}
                          onToggle={() => setBacking(backingThis ? null : m.key)} />
                      </td>
                    </tr>
                    {backingThis && (
                      <tr className="border-b border-border/50 bg-secondary/40">
                        <td colSpan={7} className="p-0">
                          <div className={PANEL_CELL}>
                            <BackPanel fixtureId={fixture.fixture_id} market={m}
                              onDone={() => setBacking(null)} />
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            </div>
            <BandKey note="Landed = how often this team hit the line in its own games on this venue. Colour follows that, not the model's probability." />
            {/* THE EVIDENCE, IN THE SAME CARD AS THE PRICE IT SUPPORTS.
                These were two sections a page apart showing the same thing twice: the
                ladder's "Landed" column IS the consistency chart's hit count, and a reader
                comparing them had to scroll past the match total, the post composer and a
                shot panel to do it. One card per team now — price at the top, the games it
                came from underneath, and the split tabs govern both. */}
            <TeamBreakdown team={g.team} title={g.label} highlight={g.key} embedded
                           fixture={fixture} leagueName={data.league_name} />
          </div>
        ))}
      </div>

      {/* Below the team tables now, and it says why. A total is not a worse market, it
          is a market with one more assumption in it, and the page should not present the
          two as interchangeable just because they sit on the same fixture. */}
      <TotalCorners
        blurred={blurred}
        canPrice={canPrice}
        markets={model.markets}
        home={home_team}
        away={away_team}
        homeName={fixture.home_name}
        awayName={fixture.away_name}
        odds={odds}
        setOdds={setOdds}
        submitOdds={submitOdds}
        flash={flash}
        fixtureId={fixture.fixture_id}
        backing={backing}
        onBacking={setBacking}
      />

      {/* AFTER THE LADDERS, because it posts what they say. The pick is chosen off a
          priced line, so the composer belongs below the prices rather than above them —
          and the price it quotes is the one already typed in, never a second copy. */}
      <PostPick
        fixture={fixture}
        markets={model.markets}
        card={data.card || {}}
        lambdas={model.lambdas}
        leagueName={data.league_name}
      />

      {/* CAVEATS LAST, AND THAT IS THE ORDER THE RESEARCH IS DONE IN. This sat above the
          prices, which asked a reader to weigh "they might get a red card" before they had
          seen a single number — so the first thing on the page was a reason to doubt a claim
          nobody had made yet. It belongs where it is useful: after the evidence and the
          price, as the last pass before backing something. */}
      <KeyFactors factors={keyFactors} homeName={fixture.home_name} awayName={fixture.away_name} />

    </div>
  );
}

// The key for the bands above. Colour is only useful if its meaning is stated — the
// fixture board learned the same lesson.
// A MODEL NUMBER A NON-MEMBER DOES NOT GET.
//
// `undefined` in one of these columns is the SERVER having removed it — see _blur_model —
// and it has to read differently from "you have not typed a price yet", which is also a
// blank. A dash for both would make a locked board look like an empty one, and the visitor
// would conclude the site has nothing rather than that it is holding something back.
function Locked() {
  return (
    <span className="text-muted-foreground/70" title="The model's price and edge are for members">
      <Lock className="inline h-3 w-3 align-[-1px]" />
    </span>
  );
}

/** Render a model number, or the lock when the server withheld it. */
const modelNum = (v, render, blurred) => {
  if (v != null) return render(v);
  return blurred ? <Locked /> : "\u2014";
};

function BandKey({ note }) {
  return (
    <div className="px-3 py-2 border-t border-border flex items-center gap-2 flex-wrap text-[10px] text-muted-foreground">
      {[70, 50, 30, 0].map((p) => {
        const c = band(p);
        return (
          <span key={p} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono-data ${c.chip} ${c.text}`}>
            {p === 70 ? "70%+" : p === 50 ? "50-69%" : p === 30 ? "30-49%" : "<30%"} {c.label}
          </span>
        );
      })}
      {note && <span className="w-full">{note}</span>}
    </div>
  );
}

// Prices in bulk, because that is how they arrive: copied off a bookmaker's coupon as
// a block of lines. Typing eight totals into eight boxes is eight chances to fat-finger
// a price into the wrong row, and the parser behind this already handled the block —
// it just had nothing to type into.
function PastePrices({ value, onChange, target, onTarget, onSubmit, homeName, awayName }) {
  const targets = [
    { key: "total", label: "Total" },
    { key: "home", label: homeName },
    { key: "away", label: awayName },
  ];
  return (
    <details className="bg-card border border-border rounded-lg" data-testid="paste-prices">
      <summary className="px-4 py-3 cursor-pointer list-none flex items-center gap-2 text-sm
                          font-head font-semibold hover:text-primary transition-colors
                          [&::-webkit-details-marker]:hidden">
        <ClipboardPaste className="h-4 w-4 text-muted-foreground" />
        Paste prices
        <span className="font-sans font-normal text-xs text-muted-foreground ml-1">
          — fill every line at once
        </span>
      </summary>
      <div className="px-4 pb-4 space-y-2">
        <textarea
          data-testid="paste-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder={"Over 9.5  1.85\nOver 10.5  2.30\n11+  3.10"}
          className="w-full bg-black border border-border rounded px-2 py-1.5 font-mono-data
                     text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Lines without a name go to
          </span>
          {targets.map((t) => (
            <button key={t.key} onClick={() => onTarget(t.key)}
              data-testid={`paste-target-${t.key}`}
              className={`text-xs px-2 py-1 rounded border transition-colors max-w-[10rem] truncate ${
                target === t.key
                  ? "bg-primary/15 border-primary/40 text-primary"
                  : "bg-secondary border-border text-muted-foreground hover:text-foreground"}`}>
              {t.label}
            </button>
          ))}
          <button onClick={onSubmit} disabled={!value.trim()}
            data-testid="paste-submit"
            className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-md bg-primary
                       text-black hover:opacity-90 transition-opacity disabled:opacity-40">
            Price them
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          One line each: a line and a price. Both <span className="text-foreground">Over 9.5 1.85</span>{" "}
          and <span className="text-foreground">10+ 1.85</span> work, and they mean the same
          thing. Name a team in the line and it routes itself.
        </p>
      </div>
    </details>
  );
}

// TOTAL CORNERS: what the model makes it, what you can get, and the gap between them.
//
// This table used to show hit rates ONLY, with the fair-odds and EV columns stripped out.
// That was right at the time and is not any more, and the difference is where the book
// price comes from. Back then the odds collection was filled by `seed_data`, which
// invented a price by jittering the model's own fair odds — so "EV" was the model
// marking its own homework and every green number was noise. `seed_data` is dead code
// now: the only writer to that collection is POST /fixtures/{id}/odds, which is you
// typing in what the shop is offering. A gap against a real price is worth showing.
//
// LANDED STAYS, next to the model column and ahead of both prices. The fair odds come
// off a Poisson fitted to the two teams' scoring rates, and the hit rate is what those
// fixtures actually did; when the two disagree, that is information, and burying it
// under a green EV badge is how a model gets believed past its evidence.
//
// The GAP column is deliberately separate from EV. The gap is what you eyeball at the
// shop — model says 2.10, you can get 2.35, that is a quarter of a point in hand. EV is
// the same fact as a percentage of stake, which is the one that adds up over a season.
// Showing both means the quick check and the arithmetic agree in front of you.

function TotalCorners({ markets, home, away, homeName, awayName,
                        odds, setOdds, submitOdds, flash,
                        fixtureId, backing, onBacking, blurred, canPrice }) {
  // Straight off the model's own total ladder, so the prices and the hit rates cannot
  // drift onto different lines. Over 9.5 is displayed as "10+", which is how it is said.
  const rows = (markets || [])
    .filter((m) => m.group === "total")
    .map((m) => ({ ...m, plus: Math.ceil(m.line ?? parseFloat(String(m.key).split("_").pop())) }))
    .filter((r) => Number.isFinite(r.plus));

  // Newest first, as the API hands them over. Kept as games rather than bare numbers so
  // each one can be shown and coloured individually.
  const totals = (team) => (team?.recent || []).filter((g) => g.total != null);
  const homeTotals = totals(home);
  const awayTotals = totals(away);
  const sample = homeTotals.length + awayTotals.length;

  if (!rows.length) return null;

  const hits = (arr, plus) => arr.filter((g) => g.total >= plus).length;

  // WHAT ACTUALLY HAPPENED, game by game, instead of a ratio. "4/4" says a line kept
  // clearing; it does not say whether that was 12, 11, 13, 12 — miles clear — or 8, 8,
  // 8, 8 against a line of 8, which is four coin flips that all landed the right way.
  // The numbers are the evidence; the fraction was only ever a summary of them.
  const CHIPS = 4;
  const Chips = ({ games, plus, label, title }) => (
    <span className="inline-flex items-center gap-1" title={title}>
      <span className="text-[9px] text-muted-foreground/70 w-3">{label}</span>
      {games.length === 0 ? <span className="text-muted-foreground text-xs">—</span>
        : games.slice(0, CHIPS).map((g, i) => (
          <span key={i}
            title={`${g.total} corners ${g.home ? "vs" : "@"} ${g.opponent}`}
            className={`inline-flex h-5 min-w-5 px-1 items-center justify-center rounded text-[10px] ${
              g.total >= plus ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
            {g.total}
          </span>
        ))}
    </span>
  );

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden"
      data-testid="total-corners-landed">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-muted-foreground" />
        <h3 className="font-head font-semibold text-sm">Total Match Corners</h3>
        {/* Stated on the card, not just in the layout: someone who scrolled straight
            here should still meet the caveat that put it second. */}
        <span className="hidden sm:inline text-[11px] text-muted-foreground">
          needs both sides to turn up — the team lines above need one
        </span>
        <span className="ml-auto font-mono-data text-[10px] text-muted-foreground"
          title={`${homeTotals.length} ${homeName} games + ${awayTotals.length} ${awayName} games`}>
          {sample} games
        </span>
      </div>
      {/* Wide on a phone: the card clips, so the table needs its own scroller. */}
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            {/* NINE COLUMNS DOWN TO SEVEN. Home count, Away count and a progress bar all
                said the same thing three ways; the last four games from each side say it
                better and in less room. Model folds under Fair, being the same fact as a
                percentage. */}
            <th className="text-left font-medium px-3 py-2">Line</th>
            <th className="text-left font-medium px-3 py-2 w-full"
              title="The last four match totals for each side, newest first. Green cleared this line, red did not.">
              Recent — {homeName} / {awayName}
            </th>
            <th className="text-right font-medium px-3 py-2" title="Across both sides' recent games">Landed</th>
            <th className="text-right font-medium px-3 py-2"
              title="The price the model's probability is worth — no margin, no juice — with that probability beneath">Fair</th>
            <th className="text-right font-medium px-3 py-2"
              title="What you can actually get. Type it in and the gap and EV fill themselves">Your price</th>
            <th className="text-right font-medium px-3 py-2"
              title="Your price minus the fair price. Positive means you are being paid over the odds">Gap</th>
            <th className="text-right font-medium px-3 py-2"
              title="The gap as a share of your stake, over the long run">EV</th>
            <th className="sticky right-0 bg-card px-2 py-2" />
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm">
          {rows.map((m) => {
            const h = hits(homeTotals, m.plus);
            const a = hits(awayTotals, m.plus);
            const pct = sample ? Math.round(((h + a) / sample) * 100) : null;
            const c = band(pct ?? 0);
            const t = m.tier ? tierMeta[m.tier] : null;
            // The gap is only meaningful once BOTH prices exist. A "gap" computed
            // against a blank input would read as the model calling every line value.
            const gap = (m.book_odds && m.fair_odds) ? m.book_odds - m.fair_odds : null;
            const backingThis = backing === m.key;
            return (
              <Fragment key={m.key}>
              <tr data-testid={`total-landed-${m.plus}`}
                className={`transition-colors ${backingThis ? "" : "border-b border-border/50"} ${flash?.[m.key] ? "flash-green" : ""}`}>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${c.chip} ${c.text}`}>{m.plus}+</span>
                </td>
                <td className="px-3 py-2 w-full">
                  <span className="flex items-center gap-3 flex-wrap">
                    <Chips games={homeTotals} plus={m.plus} label="H" title={homeName} />
                    <Chips games={awayTotals} plus={m.plus} label="A" title={awayName} />
                  </span>
                </td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  {pct == null ? <span className="text-muted-foreground text-xs">—</span> : (
                    <span className={c.text}>
                      <span className="font-semibold">{h + a}/{sample}</span>
                      <span className="ml-1 text-[10px]">{pct}%</span>
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right text-foreground leading-tight">
                  {modelNum(m.fair_odds, (v) => v.toFixed(2), blurred)}
                  <span className="block text-[10px] text-muted-foreground font-sans">
                    {m.prob != null ? `${Math.round(m.prob)}%` : ""}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  {canPrice ? (
                    <input
                      data-testid={`odds-input-${m.key}`}
                      inputMode="decimal"
                      value={odds?.[m.key] || ""}
                      onChange={(e) => setOdds({ ...odds, [m.key]: e.target.value })}
                      onBlur={() => odds?.[m.key] && submitOdds(odds)}
                      onKeyDown={(e) => e.key === "Enter" && submitOdds(odds)}
                      placeholder="—"
                      className="w-16 bg-black border border-border rounded px-1.5 py-1 text-right text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                    />
                  ) : modelNum(m.book_odds, (v) => v.toFixed(2), blurred)}
                </td>
                <td className={`px-3 py-2 text-right text-xs ${
                  gap == null ? "text-muted-foreground"
                    : gap > 0 ? "text-emerald-400" : "text-red-400"}`}
                  title={gap == null ? "Type a price to see the gap"
                    : `Model ${m.fair_odds?.toFixed(2)} · yours ${m.book_odds?.toFixed(2)}`}>
                  {gap == null ? "—" : `${gap > 0 ? "+" : ""}${gap.toFixed(2)}`}
                </td>
                <td className={`px-3 py-2 text-right font-semibold ${t ? t.text : "text-muted-foreground"}`}>
                  {modelNum(m.ev, (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`, blurred)}
                </td>
                {/* The totals table could be priced but never backed — the button existed
                    only on the team tables, so the market at the top of the page was the
                    one market you could not put on the board. */}
                <td className="sticky right-0 bg-card px-2 py-2 text-right">
                  <BackButton market={m} open={backingThis}
                    onToggle={() => onBacking(backingThis ? null : m.key)} />
                </td>
              </tr>
              {backingThis && (
                <tr className="border-b border-border/50 bg-secondary/40">
                  <td colSpan={8} className="p-0">
                    <div className={PANEL_CELL}>
                      <BackPanel fixtureId={fixtureId} market={m} onDone={() => onBacking(null)} />
                    </div>
                  </td>
                </tr>
              )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
      <BandKey note="Landed in = how often both teams' recent games cleared this total. Colour follows that, not the model." />
      <div className="px-3 py-2 text-[10px] text-muted-foreground leading-relaxed border-t border-border space-y-1">
        <p>
          <span className="text-foreground">Reading a row:</span> the model prices the line
          at <span className="text-foreground">Fair</span>. Type what the shop is
          offering into <span className="text-foreground">Your price</span> and the gap
          and EV fill in. +5% EV means that for every £10 staked, the model reckons you
          are getting £10.50 of value — over one bet that is nothing, over a season it is
          the whole game.
        </p>
        <p>
          <span className="text-foreground">One more assumption than a team line.</span>{" "}
          A team total needs that side to keep doing what it has been doing. A match total
          needs both of them to, and the opponent is a second way to be wrong that the
          price does not pay you extra for. Where a team line and this one point at the
          same game, the team line is usually the cleaner bet.
        </p>
        <p>
          <span className="text-foreground">Check it against Landed.</span> The model
          prices totals off a Poisson fitted to both sides' corner rates, which assumes
          less variation between games than corners really show — so it can be short on
          the extreme lines at either end. Where the model and the hit rate disagree
          sharply, trust neither and look at the fixture.
        </p>
        <p>
          Landed counts both sides' recent games equally and takes no account of who they
          played. It is a form guide, not a forecast.
        </p>
      </div>
    </div>
  );
}

const GoalChip = ({ label, strong }) => (
  <span
    className={`text-[10px] px-2 py-0.5 rounded border font-mono-data ${
      strong ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-secondary text-muted-foreground border-border"
    }`}
  >
    {label}
  </span>
);

const Metric = ({ label, value, accent }) => (
  <div className="flex flex-col items-center justify-center px-3 py-2 bg-secondary rounded-md min-w-[64px]">
    <span className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">{label}</span>
    <span className={`font-mono-data text-base font-semibold ${accent ? "text-primary" : "text-foreground"}`}>{value}</span>
  </div>
);

function TeamBreakdown({ team, title, highlight, embedded = false, fixture, leagueName }) {
  const [split, setSplit] = useState(highlight);
  const [count, setCount] = useState("5");
  const recentAll = team.recent || [];
  const filtered = recentAll.filter((m) => split === "overall" || (split === "home" ? m.home : !m.home));
  // ONLY THE WINDOWS THIS SPLIT CAN HONESTLY OFFER. "Last 20" over fourteen games is a tab
  // that lies, and history is capped at 20 — so on a venue split, which holds at most half
  // of it, the longer windows simply are not there.
  const windows = windowsFor(filtered);
  // A window from the previous split may not exist on this one (10 games overall, 4 at
  // home), so it falls back rather than showing an empty chart under a selected tab.
  const activeCount = windows.includes(parseInt(count, 10)) ? parseInt(count, 10) : windows[0];
  const games = filtered.slice(0, activeCount);
  const fmtDate = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  // goal-form summary over the games currently shown; games without goal data are left out
  const withGoals = games.filter((m) => m.gf != null && m.ga != null);
  const scored = withGoals.filter((m) => m.gf >= 1).length;
  const over25 = withGoals.filter((m) => m.gf + m.ga >= 3).length;
  const avgGoals = withGoals.length ? withGoals.reduce((s, m) => s + m.gf + m.ga, 0) / withGoals.length : null;
  const fhKnown = games.filter((m) => m.fh != null);
  const fhg = fhKnown.filter((m) => m.fh).length;
  const resultTone = (m) =>
    m.gf > m.ga ? "text-emerald-400" : m.gf < m.ga ? "text-red-400" : "text-zinc-400";
  // EMBEDDED MEANS "the card already exists and already names this team". Merged under the
  // price ladder there is no second card and no second title — the wrapper and the heading
  // would be a box inside a box with the team's name on both.
  const Wrap = embedded ? Fragment : "div";
  const wrapProps = embedded ? {} : { className: "bg-card border border-border rounded-lg overflow-hidden" };
  return (
    <Wrap {...wrapProps}>
      <div className={`px-4 py-3 flex items-center gap-3 ${embedded ? "border-t" : "border-b"} border-border`}>
        {embedded
          ? <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">
              The games behind it
            </span>
          : <h3 className="font-head font-semibold text-sm flex-1">{title}</h3>}
        <span
          data-testid={`bd-samples-${highlight}`}
          className={`text-[10px] px-2 py-0.5 rounded border font-mono-data ${team.real_samples >= 5 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-amber-500/15 text-amber-400 border-amber-500/30"}`}
          title="Number of real matches with corner data backing these figures"
        >
          {team.real_samples || 0} real{team.real_samples < 5 ? " · est." : ""}
        </span>
        <Tabs value={split} onValueChange={setSplit}>
          <TabsList className="bg-secondary h-8">
            {["home", "away", "overall"].map((s) => (
              <TabsTrigger key={s} value={s} data-testid={`bd-split-${highlight}-${s}`} className="text-xs px-2 h-6 capitalize">{s}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {/* THE LAST 3/5/10/SEASON AVERAGES TABLE IS GONE, and nothing replaced it because
          the graph below already answers the question it was asked. Four rows of three
          averages each is twelve numbers to hold in your head to work out whether a side
          reliably clears a line — which is exactly the reading the consistency chart does
          for you, over the window you pick. The averages themselves were also the weaker
          half: a mean of 5.4 is true of a side going 5,5,6,5,6 and of one going
          1,2,9,6,9, and the table could not tell you which you had. */}

      <ShotBlock feats={team.features?.[split]} intent={team.intent?.[split]}
        highlight={highlight} split={split} />

      {/* Per-game breakdown */}
      <div className="px-4 py-2.5 border-t border-border flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">Recent games ({split})</span>
        <Tabs value={String(activeCount)} onValueChange={setCount}>
          <TabsList className="bg-secondary h-7">
            {windows.map((c) => (
              <TabsTrigger key={c} value={String(c)} data-testid={`bd-count-${highlight}-${c}`} className="text-xs px-2.5 h-5">Last {c}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* WHAT HELD IN EVERY ONE OF THOSE GAMES, before the table they would have to work
          it out from. Everything here is already in the rows below — which is exactly the
          problem: judging whether a side reliably clears 5 means reading a column
          downwards and comparing five numbers to 5 by eye, and by eye is where the
          miscount comes from. Reads the same split and window the reader already chose. */}
      <Consistency games={games} highlight={highlight} teamName={team.name}
                   split={split} windowLabel={`last ${activeCount} games`}
                   fixture={fixture} leagueName={leagueName} />
      {withGoals.length > 0 && (
        <div className="px-4 pb-2.5 flex flex-wrap gap-2" data-testid={`bd-goalform-${highlight}`}>
          <GoalChip label={`Scored in ${scored}/${withGoals.length}`} strong={scored >= withGoals.length * 0.7} />
          {fhKnown.length > 0 && <GoalChip label={`FHG in ${fhg}/${fhKnown.length}`} strong={fhg >= fhKnown.length * 0.6} />}
          <GoalChip label={`${avgGoals.toFixed(1)} goals/g`} strong={avgGoals >= 2.8} />
          <GoalChip label={`O2.5 in ${over25}/${withGoals.length}`} strong={over25 >= withGoals.length * 0.6} />
        </div>
      )}
      <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
            <th className="text-left font-medium px-2 py-1.5 sm:px-4">Date</th>
            <th className="text-left font-medium px-2 py-1.5 sm:px-4">Opponent</th>
            <th className="text-center font-medium px-2 py-1.5">V</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4" title="Corners won">Won</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4" title="Corners conceded">Conc</th>
            <th className="text-right font-medium px-2 py-1.5 sm:px-4">Total</th>
            <th className="text-center font-medium px-2 py-1.5" title="Final score (goals for-against)">Score</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell" title="Scored a first-half goal">FHG</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell"
              title="Shots taken by this team vs shots faced. A high corner count against a side that concedes a lot of shots is a different signal from one earned against a solid defence.">Shots F–A</th>
            <th className="text-center font-medium px-2 py-1.5 hidden sm:table-cell"
              title="Shots on target, taken vs faced. Reported for only about half of fixtures, so a dash here means the provider didn't cover it — not that nothing was on target.">SoT F–A</th>
          </tr>
        </thead>
        <tbody className="font-mono-data text-sm" data-testid={`bd-recent-${highlight}`}>
          {games.length === 0 ? (
            <tr><td colSpan={10} className="px-4 py-4 text-center text-muted-foreground text-xs">No real games on this split</td></tr>
          ) : games.map((m, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
              <td className="px-2 py-1.5 sm:px-4 text-muted-foreground text-xs whitespace-nowrap">{fmtDate(m.date)}</td>
              <td className="px-2 py-1.5 sm:px-4 text-foreground font-sans text-xs whitespace-nowrap truncate max-w-[88px] sm:max-w-[140px]">{m.opponent}</td>
              <td className="px-2 py-1.5 text-center">
                <span className={`text-[9px] px-1 py-0.5 rounded ${m.home ? "bg-primary/15 text-primary" : "bg-zinc-500/15 text-zinc-400"}`}>{m.home ? "H" : "A"}</span>
              </td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-emerald-400 font-semibold">{m.won}</td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-red-400">{m.conceded}</td>
              <td className="px-2 py-1.5 sm:px-4 text-right text-foreground">{m.total}</td>
              <td className={`px-2 py-1.5 text-center text-xs font-semibold ${m.gf != null ? resultTone(m) : "text-muted-foreground"}`}
                title={scorerNote(m)}>
                {m.gf != null ? `${m.gf}-${m.ga}` : "—"}
                {m.minutes_trailing > 0 && (
                  <span className="ml-1 text-[9px] text-amber-400 font-normal"
                    title={`Spent ${m.minutes_trailing} minutes behind`}>{m.minutes_trailing}'</span>
                )}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.fh == null ? <span className="text-muted-foreground">—</span>
                  : m.fh ? <span className="text-emerald-400">✓</span>
                  : <span className="text-zinc-600">·</span>}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.shots_for == null && m.shots_against == null ? (
                  <span className="text-muted-foreground">—</span>
                ) : (
                  <span title={m.blocked_shots_for != null
                    ? `${m.blocked_shots_for} blocked`
                    : "blocked-shot detail not reported for this fixture"}>
                    <span className="text-foreground">{m.shots_for ?? "?"}</span>
                    <span className="text-muted-foreground">–</span>
                    <span className="text-muted-foreground">{m.shots_against ?? "?"}</span>
                  </span>
                )}
              </td>
              <td className="px-2 py-1.5 text-center text-xs hidden sm:table-cell">
                {m.shots_on_target_for == null && m.shots_on_target_against == null ? (
                  <span className="text-muted-foreground" title="not reported for this fixture">—</span>
                ) : (
                  <span>
                    <span className="text-foreground">{m.shots_on_target_for ?? "?"}</span>
                    <span className="text-muted-foreground">–</span>
                    <span className="text-muted-foreground">{m.shots_on_target_against ?? "?"}</span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <GoalDetail profile={team.goal_profile?.[split]} highlight={highlight} split={split} />
    </Wrap>
  );
}

// THE MISMATCH — a side that keeps winning corners against one that keeps shipping them.
//
// WHY IT IS A SECTION AND NOT A LINE ON THE STREAK PANEL. The two boards each tell half:
// team-corner streaks say who wins them, conceded streaks say who ships them. Pairing them
// by hand means holding one board in your head while scrolling the other, and the answer
// only matters when the two sides are actually playing each other — which is here.
//
// ONE SHARED LINE, NOT TWO BEST ONES. "Arsenal won 5+ in 5 of 5 · Brighton conceded 5+ in 4
// of 5" is one claim about one number. Quoting each side at its own best line would read
// stronger and mean less, because the halves would stop being about the same bet.
//
// AND IT IS A WAY TO FIND A SPOT, NOT A PRICE. measure_chase_board replayed the conceded
// ordering against a floor measured on data with no edge in it, and it did not rank. So the
// panel describes and the caveat is on it, same as every other run on this site.
//
// THE WINDOW IS FIXED AT FIVE rather than following the team panels below. This is a
// headline claim meant to be read once and shared, and a claim whose meaning changes with a
// toggle somewhere else on the page is not one — the share image would also have to name
// which window it was built from, every time.
const MISMATCH_WINDOW = 5;

function Mismatch({ home, away, fixture, leagueName }) {
  const rows = mismatches((home?.recent || []).slice(0, MISMATCH_WINDOW),
                          (away?.recent || []).slice(0, MISMATCH_WINDOW),
                          fixture?.home_name || "", fixture?.away_name || "");
  if (!hasMismatch(rows)) return null;
  const best = rows[0];

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden"
             data-testid="mismatch">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <Swords className="h-4 w-4 text-primary" />
        <h3 className="font-head font-semibold text-sm">The mismatch</h3>
        <span className="font-sans font-normal text-xs text-muted-foreground"
              data-testid="mismatch-headline">
          — {mismatchHeadline(best)}
        </span>
        {/* SHAREABLE, because this is the one claim on the page worth posting: it is made
            of facts anyone can check and it gives away no price. */}
        <div className="ml-auto flex items-center gap-2">
          <StoryButton
            days={[{ key: `mismatch-${fixture?.fixture_id}` }]}
            testId="mismatch-story"
            label="Image"
            title="A picture of this mismatch for Telegram — the record, no price"
            render={(canvas) => renderMismatchStory(canvas, {
              mismatch: best, fixture, leagueName, kickoff: kickoffLabel(fixture?.date),
            })}
          />
          <ShareButtons
            buildX={mismatchShare({ mismatch: best, fixture, leagueName })}
            xRows={2}
            text={mismatchShare({ mismatch: best, fixture, leagueName })(2)}
          />
        </div>
      </div>

      <div className="px-4 pt-4 pb-3 space-y-3">
        {rows.map((m) => (
          <div key={`${m.attacker}-${m.line}`} data-testid="mismatch-row"
               className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <MismatchHalf kicker="WINS THEM" name={m.attacker} line={m.line}
                          hits={m.attack} values={m.attackValues} tone="for" />
            <MismatchHalf kicker="SHIPS THEM" name={m.defender} line={m.line}
                          hits={m.defence} values={m.defenceValues} tone="against" />
          </div>
        ))}
        <p className="text-[11px] text-muted-foreground">
          Both records over their last {MISMATCH_WINDOW} games. What already happened, not a
          forecast — the ordering was measured against a null and does not rank.
        </p>
      </div>
    </section>
  );
}

const MISMATCH_TONE = {
  for: { text: "text-emerald-400", bar: "bg-emerald-500", border: "border-emerald-500/40" },
  against: { text: "text-red-400", bar: "bg-red-500", border: "border-red-500/40" },
};

function MismatchHalf({ kicker, name, line, hits, values, tone }) {
  const t = MISMATCH_TONE[tone];
  const peak = Math.max(...values, 1);
  return (
    <div className={`rounded border ${t.border} bg-secondary/30 px-3 py-2.5`}>
      <p className={`text-[10px] uppercase tracking-wider ${t.text}`}>{kicker}</p>
      <p className="text-sm font-medium mt-0.5 truncate">{name}</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className={`font-mono-data text-2xl font-bold ${t.text}`}>
          {hits.hits}/{hits.n}
        </span>
        <span className="text-xs text-muted-foreground">
          games at <span className="text-foreground font-medium">{line}+</span>
        </span>
      </p>
      {/* The same bars as the chart below, at a glance size. Oldest on the left. */}
      <div className="mt-2 flex items-end gap-[3px] h-8">
        {values.slice().reverse().map((v, i) => (
          <span key={i} title={`${v}`}
            className="flex-1 min-w-0 flex flex-col justify-end h-full">
            <span className={`w-full rounded-t ${v >= line ? t.bar : "bg-slate-600/70"}`}
                  style={{ height: `${Math.max(8, (v / peak) * 100)}%` }} />
          </span>
        ))}
      </div>
      <div className="flex gap-[3px] mt-1">
        {values.slice().reverse().map((v, i) => (
          <span key={i}
            className="flex-1 min-w-0 text-center font-mono-data text-[9px] text-muted-foreground">
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}

// WHAT HOLDS UP OVER THE GAMES SHOWN — drawn in the same language as the probability
// chart at the top of the page, on purpose. One vertical bar per column, brand cyan for
// the ones inside the claim and slate for the ones outside, a line picker underneath, and
// the split named in words. A reader who has understood one of the two charts has
// understood both, and the page stops looking like two products bolted together.
//
// AND IT IS THE OPPOSITE CONTENT, WHICH IS WHY THE HEADING SAYS SO. The chart above draws
// the MODEL'S distribution — one bar per possible corner count, a forecast. This draws the
// GAMES THAT HAPPENED — one bar per match, a record. Identical styling over opposite
// meanings is only safe while each one says which it is, so the caption under the headline
// is load-bearing rather than decoration.
//
// THE PICKER OPENS ON THE FLOOR, so the chart opens fully lit and the first thing a reader
// sees is the claim that holds rather than one they have to go hunting for. The floor is
// the headline and not the average: a mean of 5.4 is true of a side going 5,5,6,5,6 and of
// one going 1,2,9,6,9, and only the first is worth a line at 5.
//
// THE BIG NUMBER IS A FRACTION, NOT A PERCENTAGE. "100%" off five games is the overclaim
// this whole page is careful not to make; "5/5" carries its own sample size.
function Consistency({ games, highlight, teamName, split, windowLabel, fixture, leagueName }) {
  const [subjectKey, setSubjectKey] = useState("won");
  const [line, setLine] = useState(null);
  const [hover, setHover] = useState(null);

  const rows = consistencyRows(games);
  // ONLY THE SUBJECTS THAT HAVE DATA GET A BUTTON. Shots are the case: the provider covers
  // them for roughly half of fixtures, so offering the tab unconditionally means tapping it
  // empties the chart — and because the component returns null on no bars, it would take
  // the whole panel with it. A subject nobody can chart should not be offered.
  const offered = CONSISTENCY_SUBJECTS.filter((s) => rows.some((r) => r.key === s.key));
  const subject = offered.find((s) => s.key === subjectKey) || offered[0];
  const values = subject ? valuesFor(games, subject.pick) : [];
  const bars = subject ? gameBars(games, subject.pick) : [];
  const lines = lineWindow(values);
  // A line held over from the previous subject is meaningless on this one — conceded and
  // match total run on different scales — so it falls back whenever it is off the window.
  const active = line != null && lines.includes(line) ? line : defaultLine(values);

  if (!subject || !bars.length || active == null) return null;

  const at = hitsAt(values, active);
  const peak = Math.max(...values, 1);
  // ONE DESCRIPTION OF THE PICTURE, used by both the still and the video, so the two cannot
  // show different games — the same arrangement renderFixtureStory uses.
  const storyArgs = {
    teamName: teamName || "",
    values: bars.map((b) => b.value),
    line: active,
    hits: at.hits,
    n: at.n,
    claim: subject.claim(active),
    windowLabel,
    venueLabel: split === "overall" ? "" : split === "home" ? "at home" : "away",
    opponentLabel: fixture
      ? `${fixture.home_name === teamName ? "vs" : "@"} ${
          fixture.home_name === teamName ? fixture.away_name : fixture.home_name}`
      : "",
    leagueId: fixture?.league_id || "",
    leagueName: leagueName || "",
    kickoff: kickoffLabel(fixture?.date),
  };
  const shown = hover != null ? bars.find((b) => b.key === hover) : null;
  const everyGame = at.hits === at.n;

  return (
    <div className="px-4 pt-3 pb-4 border-t border-border" data-testid={`bd-consistency-${highlight}`}>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <BarChart3 className="h-4 w-4 text-primary" />
        <h4 className="font-head font-semibold text-sm">What holds up?</h4>
        {/* THE CHART AS A POST, still or animated — the same two buttons the probability
            chart at the top of the page offers, over the opposite content. Both render from
            the LINE AND WINDOW currently selected, so the picture is the chart the reader is
            looking at rather than a second opinion about it. */}
        <StoryButton
          days={[{ key: `form-${highlight}-${active}-${bars.length}` }]}
          testId={`form-story-${highlight}`}
          label="Image"
          title="A picture of this record for Telegram — no price on it"
          render={(canvas) => renderFormStory(canvas, storyArgs)}
        />
        {canRecord() && (
          <StoryButton
            days={[{ key: `form-${highlight}-${active}-${bars.length}` }]}
            testId={`form-video-${highlight}`}
            icon={Video}
            label="Video"
            title="A 5-second video — the bars draw in and the count climbs"
            makeFile={async (day) => {
              const canvas = document.createElement("canvas");
              const { blob, mime, type, ext } = await recordStoryVideo(canvas, (p) =>
                renderFormStory(canvas, { ...storyArgs, progress: p }));
              // `type`, not `mime`: a file typed "video/mp4;codecs=avc1…" is refused by the
              // Android share sheet. Same reason the fixture story does this.
              const container = extFor(mime);
              return new File([blob], `corner-model-${day.key}.${ext || container}`,
                              { type: type || `video/${container}` });
            }}
          />
        )}
        <div className="ml-auto flex rounded-md bg-secondary p-0.5">
          {offered.map((s) => (
            <button key={s.key} data-testid={`bd-cs-subject-${highlight}-${s.key}`}
              onClick={() => { setSubjectKey(s.key); setLine(null); }}
              className={`text-[11px] px-2 py-1 rounded transition-colors ${
                subjectKey === s.key ? "bg-primary text-primary-foreground font-medium"
                                     : "text-muted-foreground"}`}>
              {s.short}
            </button>
          ))}
        </div>
      </div>

      {/* The headline, in the same shape as the chart above: one big figure and the claim
          it belongs to spelled out underneath. */}
      <div className="flex items-end gap-3 flex-wrap mb-4">
        <div>
          <p className={`font-mono-data text-4xl font-bold leading-none ${
              everyGame ? "text-primary" : "text-foreground"}`}
            data-testid={`bd-cs-headline-${highlight}`}>
            {at.hits}/{at.n}
          </p>
          {/* THE CAPTION THAT KEEPS THE TWO CHARTS APART. "games" and past tense, against
              the "chance of" above it. */}
          <p className="text-xs text-muted-foreground mt-1.5">
            {everyGame ? "every game" : "of these games"} had{" "}
            <span className="text-foreground font-medium">{active}+ {subject.noun}</span>
          </p>
        </div>
        <div className="ml-auto text-right">
          <p className="font-mono-data text-xl text-foreground leading-none">
            {Math.min(...values)}–{Math.max(...values)}
          </p>
          {/* The spread, because a floor and an average together still do not separate
              4,4,5,5 from 4,9,4,9 — and the second is not the same bet. */}
          <p className="text-[10px] text-muted-foreground mt-1">lowest to highest</p>
        </div>
      </div>

      {/* One bar per game, oldest on the left — the same direction as the distribution's
          ascending axis above. `role=img` with a spoken summary, because the bars are not
          readable by a screen reader and the table below is the long form. */}
      <div className="relative" role="img"
        aria-label={`${subject.label} in each of the last ${bars.length} games. ${at.hits} of ${at.n} reached ${active} or more.`}>
        {shown && (
          <div className="absolute -top-1 left-0 right-0 text-center pointer-events-none z-10">
            <span className="inline-block bg-secondary border border-border rounded px-2 py-1 text-[11px] font-mono-data">
              {shown.value} {shown.home ? "vs" : "@"} {shown.opponent}
            </span>
          </div>
        )}
        <div className="flex items-end gap-[3px] h-24" data-testid={`bd-cs-bars-${highlight}`}>
          {bars.map((b) => {
            const inClaim = b.value >= active;
            return (
              <button key={b.key} type="button" data-testid={`bd-cs-bar-${highlight}-${b.key}`}
                data-in-claim={inClaim ? "1" : "0"}
                onMouseEnter={() => setHover(b.key)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(b.key)} onBlur={() => setHover(null)}
                // Tapping a game sets the line to what it produced — the same "tap a bar to
                // move the line" the chart above offers, and the quickest way to ask "how
                // many games matched this one?"
                onClick={() => lines.includes(b.value) && setLine(b.value)}
                title={`${b.value} ${subject.noun} ${b.home ? "vs" : "@"} ${b.opponent}`}
                aria-label={`${b.value} ${subject.noun} against ${b.opponent}`}
                className="flex-1 min-w-0 flex flex-col justify-end h-full group cursor-pointer">
                <span className={`w-full rounded-t transition-colors ${
                    inClaim ? "bg-primary group-hover:bg-primary/80"
                            : "bg-slate-600/70 group-hover:bg-slate-500"
                  } ${hover === b.key ? "ring-2 ring-foreground/40" : ""}`}
                  style={{ height: `${Math.max(4, (b.value / peak) * 100)}%` }} />
              </button>
            );
          })}
        </div>
        <div className="flex gap-[3px] mt-1.5">
          {bars.map((b) => (
            <span key={b.key}
              className="flex-1 min-w-0 text-center font-mono-data text-[9px] text-muted-foreground">
              {b.value}
            </span>
          ))}
        </div>
      </div>

      {/* The legend, in words. Both regions named — never colour on its own. */}
      <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
        <span className="inline-block h-2 w-2 rounded-sm bg-primary align-middle mr-1" />
        <span className="text-foreground">{active} or more</span> ({at.hits} game{at.hits === 1 ? "" : "s"})
        <span className="mx-2 text-muted-foreground/40">·</span>
        <span className="inline-block h-2 w-2 rounded-sm bg-slate-600/70 align-middle mr-1" />
        under {active} ({at.n - at.hits}).
        {" "}Tap a bar to move the line.
      </p>

      {/* The line picker, same as the chart above — a row of labelled buttons is
          discoverable and a bar is not. */}
      <div className="flex flex-wrap gap-1 mt-2.5" data-testid={`bd-cs-lines-${highlight}`}>
        {lines.map((l) => (
          <button key={l} data-testid={`bd-cs-line-${highlight}-${l}`} onClick={() => setLine(l)}
            className={`font-mono-data text-[11px] px-2 py-1 rounded border transition-colors ${
              l === active ? "border-primary/60 bg-primary/15 text-primary"
                           : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30"}`}>
            {l}+
          </button>
        ))}
      </div>

      {/* Both floors in one line, so the section says something before it is explored — and
          the caveat, on the panel that most invites the opposite reading. */}
      <p className="text-[11px] text-muted-foreground mt-3">
        <span className="text-foreground">{consistencyHeadline(rows)}</span>
        <span className="mx-2 text-muted-foreground/40">·</span>
        what already happened over these games, not a forecast
      </p>
    </div>
  );
}

// Shot volume, and the intent term the LIVE model derives from it. The backend builds
// `intent` with the same call pricing makes, so this panel cannot describe one thing
// while the price does another — including which branch fired (v3 blocked shots, or the
// v2 shots fallback for a team without enough blocked history).
const SHOT_COLS = [
  ["shots", "Shots"],
  ["shots_on_target", "On target"],
  ["blocked_shots", "Blocked"],
  // dangerous_attacks is deliberately absent: the provider returns it empty for these
  // leagues (0/40 on the coverage check), so a column for it would only ever read "—"
];

function ShotBlock({ feats, intent, highlight, split }) {
  if (!feats) return null;
  const covered = feats.covered?.shots ?? 0;
  if (!covered) {
    return (
      <div className="px-4 py-2.5 border-t border-border text-[11px] text-muted-foreground"
        data-testid={`bd-shots-empty-${highlight}`}>
        No shot data on this split yet — run the shots backfill in Tools.
      </div>
    );
  }
  const pct = intent ? (intent.multiplier * intent.form - 1) * 100 : 0;
  const dir = pct >= 0.05 ? "lifts" : pct <= -0.05 ? "cuts" : "leaves";
  const tone = pct >= 0.05 ? "text-emerald-400" : pct <= -0.05 ? "text-red-400" : "text-muted-foreground";
  return (
    <div className="px-4 py-3 border-t border-border space-y-2.5" data-testid={`bd-shots-${highlight}`}>
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">
          Shot volume ({split})
        </span>
        <span className="text-[10px] text-muted-foreground font-mono-data"
          title="Games on this split that actually carry the stat">
          {covered}/{feats.played} covered
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {SHOT_COLS.map(([key, label]) => (
          <Metric key={key} label={label}
            value={feats[`${key}_for`] != null ? feats[`${key}_for`].toFixed(1) : "—"}
            accent={key === "blocked_shots" && intent?.source === "blocked"} />
        ))}
      </div>

      {intent && (
        <div className="rounded-md border border-border bg-secondary/50 px-3 py-2"
          data-testid={`bd-intent-${highlight}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {intent.source === "blocked" ? "v3 intent · blocked shots"
                : intent.source === "shots" ? "v2 fallback · shots"
                : "no intent applied"}
            </span>
            <span className={`ml-auto font-mono-data text-sm font-semibold ${tone}`}>
              ×{(intent.multiplier * intent.form).toFixed(3)}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {intent.source === "none" ? (
              <>Not enough history to move this team's λ — it prices at the raw corner average.</>
            ) : (
              <>
                <span className="font-mono-data text-foreground">{intent.value?.toFixed(2)}</span>
                {" vs league "}
                <span className="font-mono-data text-foreground">{intent.league_avg?.toFixed(2)}</span>
                {" at weight "}
                <span className="font-mono-data">{intent.weight}</span>
                {" — "}
                {dir === "leaves" ? "leaves λ where it is" : (
                  <>{dir} λ by <span className={`font-mono-data ${tone}`}>{Math.abs(pct).toFixed(1)}%</span></>
                )}
              </>
            )}
          </p>
          {intent.reason && (
            <p className="text-[10px] text-amber-400/80 mt-1">Why not v3: {intent.reason}</p>
          )}
        </div>
      )}
    </div>
  );
}

// Scorers and minutes come from /fixtures/events, which the goal backfill fills in.
// Matches it hasn't reached carry no goal keys at all — those read as "not covered"
// rather than as zero, because "never trailed" and "we don't know" are not the same claim.
function scorerNote(m) {
  if (!m.scorers?.length) return undefined;
  return m.scorers.map((g) => `${g.minute}' ${g.player || "?"}${g.kind === "Own Goal" ? " (og)" : ""}`).join(", ");
}

function GoalDetail({ profile, highlight, split }) {
  if (!profile || !profile.games) {
    return (
      <div className="px-4 py-2.5 border-t border-border text-[11px] text-muted-foreground"
        data-testid={`bd-goals-empty-${highlight}`}>
        No goal detail on this split yet — run the goal backfill in Tools to fill scorers and minutes.
      </div>
    );
  }
  const { minutes, first_goal: fg, windows, scorers, games, played } = profile;
  const peak = Math.max(1, ...Object.values(windows));
  return (
    <div className="px-4 py-3 border-t border-border space-y-3" data-testid={`bd-goals-${highlight}`}>
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground flex-1">
          Goal detail ({split})
        </span>
        <span className="text-[10px] text-muted-foreground font-mono-data"
          title="Matches the goal backfill has reached, out of matches played on this split">
          {games}/{played} covered
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <GoalChip label={`${minutes.trailing}′ behind/g`} strong={minutes.trailing >= 30} />
        <GoalChip label={`${minutes.leading}′ ahead/g`} strong={minutes.leading >= 30} />
        {fg.scored_first_pct != null && (
          <GoalChip label={`Scored first ${fg.scored_first_pct}%`} strong={fg.scored_first_pct >= 60} />
        )}
        {fg.avg_first_scored_min != null && (
          <GoalChip label={`1st goal ${fg.avg_first_scored_min}′`} strong={fg.avg_first_scored_min <= 30} />
        )}
        {fg.avg_first_conceded_min != null && (
          <GoalChip label={`1st conceded ${fg.avg_first_conceded_min}′`} strong={fg.avg_first_conceded_min >= 55} />
        )}
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">When they score</p>
        <div className="flex items-end gap-1 h-12">
          {Object.entries(windows).map(([label, n]) => (
            <div key={label} className="flex-1 flex flex-col items-center gap-0.5" title={`${n} goals, ${label} min`}>
              <div className="w-full rounded-t bg-primary/60" style={{ height: `${(n / peak) * 100}%` }} />
              <span className="text-[8px] text-muted-foreground whitespace-nowrap">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {scorers.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Scorers</p>
          <div className="flex flex-wrap gap-1.5">
            {scorers.map((s) => (
              <span key={s.player} title={`${s.minutes.filter((x) => x != null).join("′, ")}′`}
                className="text-[11px] px-2 py-0.5 rounded border border-border bg-secondary font-sans">
                {s.player} <span className="font-mono-data text-primary">{s.goals}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ----------------------------- A plain-English read on a team -----------------------------
// The site had the numbers and never said what they meant. "4.33 / 5.67 / 10.00" is a fact;
// "wins a lot of corners but leaks them at the other end" is a read, and only one of those
// tells a newcomer whether to care. Every trait comes from the backend with the average it
// was derived from, so nothing here is prose invented in the browser.
const TRAIT_TONE = {
  strong: "text-tone-strong-fg border-tone-strong/50 bg-tone-strong/15",
  streak: "text-tone-streak-fg border-tone-streak/50 bg-tone-streak/15",
  under: "text-tone-under-fg border-tone-under/50 bg-tone-under/15",
  edge: "text-tone-edge-fg border-tone-edge/50 bg-tone-edge/15",
};
const TRAIT_ICON = { attack: Flame, defence: Shield, venue: MapPin };

function TeamRead({ name, profile, where }) {
  if (!profile) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4" data-testid={`team-read-${where}`}>
      <div className="flex items-center gap-2 mb-2">
        <h3 className="font-head font-semibold text-sm truncate" title={name}>{name}</h3>
        <span className="ml-auto shrink-0 font-mono-data text-[10px] text-muted-foreground">
          {profile.games} {where} game{profile.games === 1 ? "" : "s"}
        </span>
      </div>
      {profile.traits?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {profile.traits.map((t) => {
            const Icon = TRAIT_ICON[t.key] || Flame;
            return (
              <span key={t.key} data-testid={`trait-${where}-${t.key}`}
                title={`${t.value} vs ${t.league_avg} league average`}
                className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border ${TRAIT_TONE[t.tone]}`}>
                <Icon className="h-3 w-3" /> {t.label}
                {t.delta_pct != null && (
                  <span className="font-mono-data opacity-80">
                    {t.delta_pct > 0 ? "+" : ""}{t.delta_pct}%
                  </span>
                )}
              </span>
            );
          })}
        </div>
      )}
      <p className="text-xs text-muted-foreground leading-relaxed">{profile.summary}</p>
    </div>
  );
}

// ----------------------------- What could change the game -----------------------------
// A corner count is decided by who has to chase. The backed team scoring first is the main
// way a corners-over dies; the opponent going a goal or a man down is the way it runs away.
// These are measured from this team's own games — except the red-card row, which carries no
// number because the provider data has no cards in it, and says so rather than implying one.
const FACTOR_META = {
  risk: { icon: TrendingDown, cls: "text-tone-under-fg border-tone-under/40 bg-tone-under/10", word: "Risk" },
  boost: { icon: TrendingUp, cls: "text-tone-strong-fg border-tone-strong/40 bg-tone-strong/10", word: "Helps" },
  watch: { icon: Eye, cls: "text-tone-streak-fg border-tone-streak/40 bg-tone-streak/10", word: "Watch" },
};

/**
 * The runs going into this game, biggest first.
 *
 * WHAT THE FIRE MEANS, AND WHAT IT DOES NOT. It marks a run of FIRE_RUN or more — the same
 * threshold the share text and the angle menu use, so one emoji means one thing across the
 * site. It is not a recommendation: measure_chase_board.py replayed four orderings
 * walk-forward and could not separate any from a shuffled control, so a run says what has
 * happened, not what will. The projection and the matchup beside it carry the argument;
 * this panel carries the evidence the reader came for.
 *
 * THE RUN AND THE RECORD ARE BOTH PRINTED because they are different numbers — "9 in a row"
 * is the current run, "9 of 9 settled" is how the window closed — and they diverge exactly
 * when it matters.
 */
function RunningStreaks({ streaks, share }) {
  const rows = fixtureStreaks(streaks);
  if (!rows.length) return null;
  return (
    <section className="bg-card border border-border rounded-lg p-3.5 sm:p-4 space-y-3"
             data-testid="fixture-streak-share">
      <div className="flex items-center gap-2 flex-wrap justify-between">
        <span className="text-sm font-medium">{streakHeadline(rows)}</span>
        <ShareButtons buildX={share} xRows={4} text={share(4)} />
      </div>
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.key} data-testid={`fixture-streak-${r.key}`}
               className="rounded border border-border/70 bg-secondary/40 px-3 py-2">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span aria-hidden="true">{r.mark}</span>
              {/* THE VERB MATTERS ON A CONCEDED ROW. "Brighton 5+" off a Brighton
                  CONCEDED streak reads as backing Brighton's own corners, which is the
                  opposite side of the angle. `claim` carries the verb. */}
              <span className="font-medium text-sm">{r.claim}</span>
              <span className={`text-sm ${r.hot ? "text-tone-streak-fg" : "text-muted-foreground"}`}>
                — {r.run} in a row
              </span>
            </div>
            {/* WHOSE corners, and where. "5+" alone is a team line and a match total at
                once, and the match number is about twice the team one. */}
            <div className="text-[11px] text-muted-foreground mt-0.5 font-mono-data">
              {streakDetail(r)}
            </div>
          </div>
        ))}
      </div>
      {/* Said once, on the panel that most invites the opposite reading. */}
      <p className="text-[11px] text-muted-foreground">
        A run is what has already happened, not a forecast. The projection above is the model's view.
      </p>
    </section>
  );
}

function HeadToHead({ h2h, homeName, awayName }) {
  // NOTHING ON FILE IS NOT THE SAME AS NEVER PLAYED, so the panel does not render at all
  // rather than printing an empty state that would have to make one claim or the other.
  // The results cache only goes back as far as this site has been syncing the
  // competition — h2h.py has the full note.
  if (!hasH2H(h2h)) return null;
  const rows = meetingRows(h2h);
  const runs = unbeatenRows(h2h);
  const record = recordLine(h2h, homeName, awayName);
  const corners = h2h.corners;

  return (
    <details className="bg-card border border-border rounded-lg" data-testid="h2h">
      <summary className="px-4 py-3 cursor-pointer list-none flex items-center gap-2 text-sm
                          font-head font-semibold hover:text-primary transition-colors
                          [&::-webkit-details-marker]:hidden">
        <History className="h-4 w-4 text-muted-foreground" />
        Previous meetings
        {/* The one line worth reading without opening it: what this pairing produces. */}
        <span className="font-sans font-normal text-xs text-muted-foreground ml-1"
              data-testid="h2h-summary">
          — {summaryLine(h2h)}
        </span>
      </summary>

      <div className="px-4 pb-4 space-y-3">
        {/* THE UNBEATEN RUNS FIRST. They are the claim a reader repeats, and burying them
            under a table means they get read off the rows by eye — which is where a
            miscount comes from. */}
        {runs.length > 0 && (
          <div className="space-y-1.5" data-testid="h2h-runs">
            {runs.map((r) => (
              <div key={r.key} data-testid={`h2h-run-${r.key}`}
                   className="rounded border border-border/70 bg-secondary/40 px-3 py-2
                              flex items-baseline gap-2 flex-wrap">
                <span className="font-medium text-sm">{r.team}</span>
                <span className="text-sm text-tone-streak-fg">{r.label}</span>
                {/* OUT OF HOW MANY, always. Three from three and three from nine are
                    different claims, and the short one sounds the strongest. */}
                <span className="text-[11px] text-muted-foreground font-mono-data">
                  ({r.played} on file)
                </span>
              </div>
            ))}
          </div>
        )}

        {corners && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground
                          font-mono-data" data-testid="h2h-corners">
            <span>avg {corners.avg_total} corners</span>
            <span>{homeName} {corners.avg_home_team} · {awayName} {corners.avg_away_team}</span>
            <span>range {corners.lowest}–{corners.highest}</span>
            <span>{corners.played} {corners.played === 1 ? "meeting" : "meetings"}</span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-[10px]
                             uppercase tracking-wider">
                <th className="text-left font-medium px-2 py-2">Date</th>
                <th className="text-left font-medium px-2 py-2">Comp</th>
                <th className="text-left font-medium px-2 py-2 w-full">Score</th>
                <th className="text-right font-medium px-2 py-2 whitespace-nowrap">Corners</th>
              </tr>
            </thead>
            <tbody className="font-mono-data text-sm">
              {rows.map((r) => (
                <tr key={r.key} className="border-b border-border/50 last:border-0"
                    data-testid="h2h-row">
                  <td className="px-2 py-2 whitespace-nowrap text-muted-foreground">
                    {r.date}
                    {/* Where it was played, from the home side's end — the same side
                        every number in the row is stated from. */}
                    <span className="ml-1 text-[10px] uppercase">{r.venue}</span>
                  </td>
                  <td className="px-2 py-2 text-[11px] text-muted-foreground whitespace-nowrap">
                    {r.competition}
                  </td>
                  {/* A MEETING WITH NO SCORE ON FILE SAYS SO. Older cache rows carry
                      corners and no goals, and rendering a blank as 0-0 would invent a
                      draw — which also reads as "unbeaten". */}
                  <td className="px-2 py-2">
                    {r.score || <span className="text-muted-foreground text-xs">score not on file</span>}
                  </td>
                  <td className="px-2 py-2 text-right whitespace-nowrap">{r.corners || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {record && (
          <p className="text-[11px] text-muted-foreground" data-testid="h2h-record">{record}</p>
        )}
        {/* Said on the panel, because an absence here is the thing most likely to be
            misread as a fact about the teams. */}
        <p className="text-[11px] text-muted-foreground">{h2h.window}</p>
      </div>
    </details>
  );
}

function KeyFactors({ factors, homeName, awayName }) {
  const sides = [["home", homeName], ["away", awayName]].filter(([k]) => (factors[k] || []).length);
  const [side, setSide] = useState(sides[0]?.[0] || "home");
  if (!sides.length) return null;
  const rows = factors[side] || [];

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden" data-testid="key-factors">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <Swords className="h-4 w-4 text-primary" />
        <h3 className="font-head font-semibold text-sm">What could change this</h3>
        {sides.length > 1 && (
          <div className="ml-auto flex rounded-md bg-secondary p-0.5">
            {sides.map(([k, label]) => (
              <button key={k} data-testid={`kf-side-${k}`} onClick={() => setSide(k)}
                className={`text-[11px] px-2 py-1 rounded transition-colors max-w-[110px] truncate ${
                  side === k ? "bg-primary text-primary-foreground font-medium" : "text-muted-foreground"}`}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <ul className="divide-y divide-border">
        {rows.map((f) => {
          const m = FACTOR_META[f.kind] || FACTOR_META.watch;
          const Icon = m.icon;
          return (
            <li key={f.key} className="px-4 py-3 flex gap-3" data-testid={`kf-${f.key}`}>
              <span className={`shrink-0 h-6 w-6 rounded-full border grid place-items-center ${m.cls}`}>
                <Icon className="h-3 w-3" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium flex items-center gap-2 flex-wrap">
                  {f.title}
                  <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${m.cls}`}>
                    {m.word}
                  </span>
                  {f.measured === false && (
                    <span className="text-[9px] uppercase tracking-wider text-muted-foreground border border-border px-1.5 py-0.5 rounded">
                      not in the data
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{f.detail}</p>
                {f.games != null && (
                  <p className="text-[10px] text-muted-foreground/70 mt-1 font-mono-data">
                    from {f.games} game{f.games === 1 ? "" : "s"}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ----------------------------- Backing an angle -----------------------------
// One tap on a market you have already priced. Everything except the stake is already on
// the row and is captured server-side — the line, the price you got, the model's price,
// the EV at that moment — so a slip records what was true WHEN IT WAS PLACED rather than
// what the model thinks about it a week later.
//
// UNITS, NOT POUNDS. The group board totals in units and never collects cash, so asking
// for cash here was the one place the denomination disagreed with itself. Units also make
// the board readable: a room betting £5 and £500 produces one number that means the same
// to both of them.
//
// PRESETS RATHER THAN A KEYBOARD. This is used on a phone, mid-scroll, deciding between
// half a point and two. Four taps cover almost every real answer; the field is still there
// for the rest.
const UNIT_PRESETS = [0.5, 1, 2, 3];

// A TRIGGER THAT STAYS ON SCREEN. These tables are seven columns wide and scroll sideways
// on a phone, and the action column is the last one — so the button that is the whole
// point of the page sat past the right edge, invisible until you thought to swipe a table
// you had no reason to think was scrollable. The cell is sticky, so the call to action
// rides along over whatever is underneath it.
export function BackButton({ market, open, onToggle }) {
  const { user } = useAuth();
  if (!user || market.book_odds == null) return null;   // nothing to bet, or nobody to bet it
  return (
    <button onClick={onToggle} data-testid={`log-bet-${market.key}`}
      title={open ? "Close" : "Back this and put it on the group board"}
      className={`text-[10px] px-2 py-1 rounded border transition-colors whitespace-nowrap ${
        open ? "border-border text-muted-foreground"
             : "border-primary/40 text-primary hover:bg-primary/10"}`}>
      {open ? "Close" : "I'm backing this"}
    </button>
  );
}

// THE FORM GETS ITS OWN ROW rather than being crammed into the action cell. Squeezed into
// the cell it wrapped onto three lines and the row grew by 70px the instant you tapped —
// the table jumped under your finger. Across the full width it is one line that reads
// left to right, it starts at the left edge so a phone sees it without scrolling, and the
// row it belongs to does not move at all.
export function BackPanel({ fixtureId, market, onDone }) {
  const [units, setUnits] = useState(1);
  // PUBLIC BY DEFAULT, and said so in words rather than hidden in a settings screen: the
  // point of the board is that the room can see what the room is on. Keeping one back is
  // still one tap, because "I want this private" is a real thing to want and burying it
  // would make people simply not log the bet at all.
  const [shared, setShared] = useState(true);
  const [busy, setBusy] = useState(false);

  const place = async () => {
    const n = Number(units);
    if (!(n > 0)) { toast.error("Pick a stake"); return; }
    setBusy(true);
    try {
      await api.placeBet({ fixture_id: fixtureId, market_key: market.key, stake: n, shared });
      toast.success(shared
        ? `Backing ${market.label} @ ${market.book_odds.toFixed(2)} — it's on the board`
        : `Logged ${market.label} @ ${market.book_odds.toFixed(2)} — kept private`);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not log that bet");
    } finally { setBusy(false); }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid={`log-bet-open-${market.key}`}>
      <span className="text-[11px] text-muted-foreground font-sans">
        <span className="text-foreground">{market.label}</span> @ {market.book_odds.toFixed(2)} —
        staking
      </span>
      <div className="inline-flex rounded-md border border-border overflow-hidden">
        {UNIT_PRESETS.map((u) => (
          <button key={u} onClick={() => setUnits(u)}
            data-testid={`log-bet-unit-${market.key}-${u}`}
            className={`text-[11px] px-2.5 py-1 transition-colors ${
              Number(units) === u ? "bg-primary text-primary-foreground font-semibold"
                                  : "text-muted-foreground hover:text-foreground"}`}>
            {u}u
          </button>
        ))}
      </div>
      <input
        value={units} onChange={(e) => setUnits(e.target.value)}
        inputMode="decimal"
        onKeyDown={(e) => { if (e.key === "Enter") place(); if (e.key === "Escape") onDone(); }}
        aria-label="Units"
        data-testid={`log-bet-units-${market.key}`}
        className="w-12 bg-black border border-border rounded px-1.5 py-1 text-right text-xs
                   focus:outline-none focus:ring-2 focus:ring-primary" />
      <button onClick={place} disabled={busy} data-testid={`log-bet-save-${market.key}`}
        className="text-[11px] px-3 py-1 rounded bg-primary text-primary-foreground font-semibold disabled:opacity-50">
        {busy ? "…" : shared ? "Back it" : "Log it"}
      </button>
      <button onClick={() => setShared((v) => !v)}
        data-testid={`log-bet-share-${market.key}`}
        className={`text-[11px] font-sans underline underline-offset-2 decoration-dotted transition-colors ${
          shared ? "text-muted-foreground hover:text-foreground" : "text-tone-streak-fg"}`}>
        {shared ? "everyone sees this" : "just for me"}
      </button>
    </div>
  );
}
