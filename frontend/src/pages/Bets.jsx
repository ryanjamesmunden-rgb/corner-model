import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Receipt, Users, Trash2, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import MembersOnly from "@/components/MembersOnly";
import { withFlag } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

// Slips: yours, and the group's.
//
// TWO TABS, TWO DIFFERENT THINGS — and they are gated differently on purpose. YOUR bets
// need an account and nothing more: it is your own record and there is nobody to protect
// it from. THE GROUP board is other people's betting, so it is members-only, the audience
// being the room that pays to be in it.
//
// NO CASH ANYWHERE ON THE GROUP TAB. The server never sends stakes for it — see
// bets_this_week — so there is nothing here to hide. What is useful to everyone else is
// WHAT was backed and AT WHAT PRICE; how much someone put on varies entirely with their
// bankroll and tells the reader nothing they can act on.

const STATUS = {
  won: { cls: "text-tone-strong-fg border-tone-strong/45 bg-tone-strong/15", Icon: TrendingUp, label: "Won" },
  lost: { cls: "text-tone-under-fg border-tone-under/45 bg-tone-under/15", Icon: TrendingDown, label: "Lost" },
  void: { cls: "text-muted-foreground border-border", Icon: Minus, label: "Void" },
  pending: { cls: "text-tone-streak-fg border-tone-streak/45 bg-tone-streak/15", Icon: Loader2, label: "Pending" },
};

function StatusChip({ status }) {
  const m = STATUS[status] || STATUS.pending;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border font-mono-data ${m.cls}`}>
      <m.Icon className="h-2.5 w-2.5" /> {m.label}
    </span>
  );
}

const signed = (n) => `${n > 0 ? "+" : ""}${n.toFixed(2)}`;

export default function Bets() {
  const { user, ready } = useAuth();
  const [tab, setTab] = useState("mine");

  if (!ready) return null;
  if (!user) {
    return (
      <MembersOnly
        title="Your bets live with your account"
        blurb="Log what you have backed and at what price, see it settle itself off the results,
               and — if you are a member — see what the rest of the room is on this week."
      />
    );
  }

  return (
    <div className="space-y-3 sm:space-y-4" data-testid="bets-page">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="font-head text-2xl font-bold tracking-tight">Bets</h1>
        <Tabs value={tab} onValueChange={setTab} className="ml-auto">
          <TabsList className="bg-secondary h-8">
            <TabsTrigger value="mine" data-testid="bets-tab-mine" className="text-xs px-3 h-6">
              <Receipt className="h-3 w-3 mr-1.5" /> Mine
            </TabsTrigger>
            <TabsTrigger value="group" data-testid="bets-tab-group" className="text-xs px-3 h-6">
              <Users className="h-3 w-3 mr-1.5" /> This week
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {tab === "mine" ? <MyBets /> : (
        <MembersOnly
          title="The group board is for members"
          blurb="What everyone else backed this week, at the price they took, and how it landed.
                 Stakes are never shown — only the selection and the price, which is the part
                 anyone else can learn from."
        >
          <GroupBets />
        </MembersOnly>
      )}
    </div>
  );
}

function MyBets() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);

  const load = useCallback(() => {
    api.bets().then(setRows).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    try { await api.deleteBet(id); setRows((r) => r.filter((b) => b.bet_id !== id)); }
    catch { toast.error("Could not remove that bet"); }
  };

  if (rows === null) return <Skeleton />;
  if (!rows.length) {
    return (
      <Empty>
        Nothing logged yet. Open a fixture, type the price your bookmaker is showing into a
        market, and a <span className="text-foreground">Log bet</span> button appears beside it.
      </Empty>
    );
  }

  const settled = rows.filter((b) => b.status === "won" || b.status === "lost");
  const profit = settled.reduce((s, b) => s + (b.profit || 0), 0);

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden" data-testid="my-bets">
      <div className="px-4 py-3 border-b border-border flex items-center gap-3 flex-wrap">
        <span className="font-head font-semibold text-sm">Your slips</span>
        <span className="font-mono-data text-[11px] text-muted-foreground">
          {rows.length} logged · {settled.length} settled
        </span>
        {settled.length > 0 && (
          <span className={`ml-auto font-mono-data text-sm font-semibold ${
            profit >= 0 ? "text-tone-strong-fg" : "text-tone-under-fg"}`}>
            {signed(profit)}
          </span>
        )}
      </div>
      <div className="divide-y divide-border">
        {rows.map((b) => (
          <div key={b.bet_id} className="px-4 py-3 flex items-start gap-3" data-testid="bet-row">
            <div className="min-w-0 flex-1">
              <button onClick={() => navigate(`/fixture/${b.fixture_id}`)}
                className="text-sm font-medium hover:text-primary transition-colors text-left truncate block max-w-full">
                {b.home_name} v {b.away_name}
              </button>
              <p className="font-mono-data text-xs text-muted-foreground mt-0.5">
                {b.market_label} @ {b.book_odds?.toFixed(2)}
                <span className="mx-1.5 opacity-40">·</span>
                {b.stake?.toFixed(2)} staked
                {b.shared === false && <span className="ml-1.5 opacity-70">· private</span>}
              </p>
              <div className="flex items-center gap-2 mt-1.5">
                <StatusChip status={b.status} />
                {b.status !== "pending" && (
                  <span className={`font-mono-data text-xs ${
                    (b.profit || 0) >= 0 ? "text-tone-strong-fg" : "text-tone-under-fg"}`}>
                    {signed(b.profit || 0)}
                  </span>
                )}
                {b.result_corners && (
                  <span className="font-mono-data text-[10px] text-muted-foreground">
                    {b.result_corners.home}–{b.result_corners.away} corners
                  </span>
                )}
              </div>
            </div>
            <button onClick={() => remove(b.bet_id)} title="Remove"
              data-testid="bet-remove"
              className="text-muted-foreground hover:text-tone-under-fg transition-colors shrink-0">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function GroupBets() {
  const [data, setData] = useState(null);
  useEffect(() => { api.betsWeek(7).then(setData).catch(() => setData({ bets: [], summary: {} })); }, []);

  if (data === null) return <Skeleton />;
  const { bets = [], summary = {} } = data;
  if (!bets.length) {
    return <Empty>Nobody has shared a bet this week yet. Yours would be the first.</Empty>;
  }

  return (
    <section className="bg-card border border-border rounded-lg overflow-hidden" data-testid="group-bets">
      <div className="px-4 py-3 border-b border-border flex items-center gap-3 flex-wrap">
        <Users className="h-4 w-4 text-primary" />
        <span className="font-head font-semibold text-sm">The room, this week</span>
        <span className="font-mono-data text-[11px] text-muted-foreground">
          {summary.count} bets · {summary.members} member{summary.members === 1 ? "" : "s"}
          {summary.avg_odds && <> · avg {summary.avg_odds.toFixed(2)}</>}
        </span>
        {summary.settled > 0 && (
          <span className={`ml-auto font-mono-data text-sm font-semibold ${
            summary.units >= 0 ? "text-tone-strong-fg" : "text-tone-under-fg"}`}
            title="Level stakes: every settled slip counted once, at the price it was taken">
            {signed(summary.units)}u
          </span>
        )}
      </div>
      <div className="divide-y divide-border">
        {bets.map((b, i) => (
          <div key={i} className="px-4 py-2.5 flex items-center gap-3" data-testid="group-bet-row">
            <div className="min-w-0 flex-1">
              <p className="text-sm truncate">
                <span className="text-primary font-medium">{b.user_name}</span>
                <span className="text-muted-foreground"> backed </span>
                <span className="font-mono-data">{b.market_label}</span>
              </p>
              <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                {withFlag(b.league_id, `${b.home_name} v ${b.away_name}`)}
                {b.kickoff && <><span className="mx-1.5 opacity-40">·</span>{kickoffLabel(b.kickoff)}</>}
              </p>
            </div>
            <span className="font-mono-data text-sm shrink-0">{b.book_odds?.toFixed(2)}</span>
            <StatusChip status={b.status} />
          </div>
        ))}
      </div>
      <p className="px-4 py-2.5 border-t border-border text-[11px] text-muted-foreground">
        Selections and prices only — stakes are never shared. The total is level stakes, one
        point a bet, so it reads the same however differently people are betting.
      </p>
    </section>
  );
}

const Skeleton = () => (
  <div className="bg-card border border-border rounded-lg p-4 space-y-2">
    {[0, 1, 2].map((i) => <div key={i} className="h-12 rounded-md bg-secondary animate-pulse" />)}
  </div>
);

const Empty = ({ children }) => (
  <p className="bg-card border border-border rounded-lg px-4 py-6 text-sm text-muted-foreground"
    data-testid="bets-empty">{children}</p>
);
