import { useState, useMemo } from "react";
import { Send, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { telegramPick } from "@/lib/shareText";

// WRITE THE PICK ONCE, POST IT TWICE.
//
// The channel post has a fixed shape — date, league, fixture, line, price, model price,
// then the evidence — and it was being typed out by hand for every pick. Slow, and worse
// than slow: the model price in the post is read off the screen and retyped, so sooner or
// later the post quotes a number the site never said.
//
// CHANNEL ONLY. There is deliberately no public version of this post: the ladder and the
// opponent's defending are what a member is paying to read, so they do not go out free on
// X. What X gets is the streak board at the top of this page — a line and how long it has
// been landing, enough to be worth a click and short of answering why.

// Books worth one tap. Anything else is typed — this is a shortcut, not a list of the
// only bookmakers that exist.
const BOOKS = ["Bet365", "Pinnacle", "Betfair", "William Hill"];
const STAKES = [0.5, 1, 1.5, 2, 3];

export default function PostPick({ fixture, markets = [], card = {}, lambdas = {}, leagueName }) {
  // THE BEST PRICED LINE, NOT THE FIRST ONE. Opening on `total_over_8.5` because it
  // happens to sort first would mean re-picking the market every single time. A priced
  // market with the best EV is what you came to post; where nothing is priced yet, the
  // model's own strongest team line is the next best guess.
  const best = useMemo(() => {
    const priced = markets.filter((m) => m.book_odds != null && m.ev != null);
    if (priced.length) return priced.reduce((a, b) => (b.ev > a.ev ? b : a)).key;
    const team = markets.filter((m) => m.group !== "total" && m.prob != null);
    return (team.length ? team.reduce((a, b) => (b.prob > a.prob ? b : a)) : markets[0])?.key;
  }, [markets]);

  const [key, setKey] = useState(best);
  const [book, setBook] = useState("Bet365");
  const [stake, setStake] = useState(1);
  const [link, setLink] = useState("");
  const [result, setResult] = useState("");
  const [copied, setCopied] = useState("");

  const market = markets.find((m) => m.key === key) || markets.find((m) => m.key === best);
  if (!fixture || !market) return null;

  const fx = { ...fixture, league_name: leagueName || fixture.league_name || "" };
  const vip = telegramPick({
    fixture: fx, market, card, lambdas,
    // The price is the one already typed into the ladder above. Retyping it here would be
    // a second place for it to be wrong.
    price: market.book_odds, book, stake, link, result: result || null,
  });

  const copy = async (what, text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      toast.error("Couldn't copy — your browser blocked clipboard access");
    }
  };

  const field = "bg-[#121212] border border-border rounded px-2 py-1.5 text-xs";
  const Pills = ({ options, value, onChange, name, fmt = (x) => x }) => (
    <div className="inline-flex rounded-md border border-border overflow-hidden">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)} data-testid={`post-${name}-${o}`}
          className={`text-[11px] px-2.5 py-1 transition-colors ${
            String(value) === String(o) ? "bg-primary text-primary-foreground font-semibold"
                                        : "text-muted-foreground hover:text-foreground"}`}>
          {fmt(o)}
        </button>
      ))}
    </div>
  );

  const Post = ({ title, note, text, what, testid }) => (
    <div className="flex-1 min-w-[280px]">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-xs font-semibold text-foreground whitespace-nowrap">{title}</span>
        <span className="hidden sm:inline text-[10px] text-muted-foreground">{note}</span>
        <button onClick={() => copy(what, text)} data-testid={`post-copy-${testid}`}
          disabled={!text}
          className="ml-auto flex items-center gap-1 text-[11px] px-2 py-1 rounded border
                     border-border text-muted-foreground hover:text-foreground
                     hover:bg-white/10 disabled:opacity-40 transition-colors">
          {copied === what ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          {copied === what ? "Copied" : "Copy"}
        </button>
      </div>
      {/* The post itself, as it will land. A preview that reflowed or restyled the text
          would hide exactly the thing worth checking before it goes out. */}
      <pre data-testid={`post-text-${testid}`}
        className="whitespace-pre-wrap break-words text-[11px] leading-relaxed font-sans
                   bg-[#121212] border border-border rounded p-3 min-h-[120px] text-foreground">
        {text || "Nothing to post for this line yet."}
      </pre>
    </div>
  );

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden" data-testid="post-pick">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <Send className="h-4 w-4 text-muted-foreground" />
        <h3 className="font-head font-semibold text-sm">Post this pick</h3>
        <span className="hidden sm:inline text-[11px] text-muted-foreground">
          members only — X gets the streaks, not the reasoning
        </span>
      </div>

      <div className="p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select value={key} onChange={(e) => setKey(e.target.value)}
            data-testid="post-market" className={`${field} font-mono-data max-w-full`}>
            {["home", "away", "total"].map((g) => {
              const rows = markets.filter((m) => m.group === g);
              if (!rows.length) return null;
              const label = g === "total" ? "Match total"
                : `${g === "home" ? fixture.home_name : fixture.away_name} corners`;
              return (
                <optgroup key={g} label={label}>
                  {/* The team is IN the option, not only in the group heading: a closed
                      select shows one line, and "6+ · model 1.64" does not say whose
                      corners it is 6 of. */}
                  {rows.map((m) => (
                    <option key={m.key} value={m.key}>
                      {g === "total" ? "Match" : (g === "home" ? fixture.home_name : fixture.away_name)}
                      {" "}{Math.ceil(m.line)}+ · model {m.fair_odds?.toFixed(2) ?? "—"}
                      {m.book_odds != null ? ` · yours ${m.book_odds.toFixed(2)}` : " · no price"}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
          <Pills options={BOOKS} value={book} onChange={setBook} name="book" />
          <Pills options={STAKES} value={stake} onChange={setStake} name="stake" fmt={(x) => `${x}u`} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input value={link} onChange={(e) => setLink(e.target.value)}
            placeholder="Bet link (optional)" data-testid="post-link"
            className={`${field} flex-1 min-w-[200px] font-mono-data`} />
          {/* SETTLED, NOT PREDICTED. The same builder writes the pick and the repost after
              the game, so the two cannot describe the same bet differently. */}
          <select value={result} onChange={(e) => setResult(e.target.value)}
            title="Reposting after the game? Mark how it landed."
            data-testid="post-result" className={`${field} w-36`}>
            <option value="">Not settled yet</option>
            <option value="win">Won ✅</option>
            <option value="loss">Lost ❌</option>
            <option value="void">Void ➖</option>
          </select>
        </div>

        {market.book_odds == null && (
          <p className="text-[11px] text-amber-400">
            No price typed for this line yet — paste one into the ladder above and the
            channel post will carry it.
          </p>
        )}

        <Post title="VIP Telegram" note="members only — price, stake and the reasoning"
          text={vip} what="vip" testid="vip" />
      </div>
    </div>
  );
}
