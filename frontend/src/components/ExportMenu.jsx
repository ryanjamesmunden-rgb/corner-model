import { useState } from "react";
import { toast } from "sonner";
import { Download, Copy, FileText, Table, Loader2, Flame, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { copyOrDownload, download, exportError } from "@/lib/exportCopy";
import { useAuth } from "@/context/AuthContext";
import { Link } from "react-router-dom";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// THE PAYWALL HAD A SIDE DOOR HERE, with a label on it.
//
// "Copy this week's streaks" and the markdown report assemble the same boards the paid
// screens show — every streak, every mismatch, the whole chase board — and this menu
// sits in the header on every page, for everybody. Gating the screens never gated these,
// because calling streaks() from inside another endpoint does not run its dependency. A
// signed-out visitor could take the entire product in one click.
//
// Both are members-only on the server now. They are still LISTED for a non-member, with
// a padlock and a route to /join, because a menu that silently loses two of its five
// items teaches nobody that there is something worth paying for.
//
// The CSVs stay open: team averages and fixture projections are the same numbers the
// free boards already show, so gating the download would only be theatre.
export default function ExportMenu() {
  const { member } = useAuth();
  const [busy, setBusy] = useState(false);

  // THE ERROR IS NAMED, NOT SWALLOWED. Every failure here used to read "Export failed",
  // which is three different problems wearing one sentence — not a member, a backend that
  // was asleep, a browser refusing the clipboard — each with a different next step.
  const run = async (fn) => {
    setBusy(true);
    try { await fn(); } catch (e) { toast.error(exportError(e)); }
    finally { setBusy(false); }
  };

  // The copy goes through copyOrDownload, which hands the clipboard the PROMISE rather
  // than awaiting the request first. Awaiting first is what broke this: the gesture that
  // permits a clipboard write expires in about five seconds, and the first request to a
  // sleeping backend takes ten times that. See lib/exportCopy.
  const said = (how, what) => toast.success(
    how === "clipboard"
      ? `${what} copied — paste into Claude`
      : `${what} downloaded — the browser would not allow a copy, so it saved the file instead`);

  const copyMd = () => run(async () => {
    const { how } = await copyOrDownload(() => api.exportMarkdown(),
                                         "corner-model-export.md");
    said(how, "All stats");
  });
  const copyStreaks = (days) => run(async () => {
    const { how } = await copyOrDownload(() => api.exportStreaks(days),
                                         `corner-model-streaks-${days}d.md`);
    said(how, `Next ${days} days of streaks`);
  });
  const dlMd = () => run(async () => {
    download(await api.exportMarkdown(), "corner-model-export.md", "text/markdown");
    toast.success("Markdown downloaded");
  });
  const dlCsv = (type) => run(async () => {
    download(await api.exportCsv(type), `corner-model-${type}.csv`, "text/csv");
    toast.success(`${type} CSV downloaded`);
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          data-testid="export-btn"
          className="flex items-center gap-2 bg-secondary hover:bg-white/10 border border-border text-sm font-medium rounded-md px-3 py-2 transition-colors duration-150"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          <span className="hidden sm:inline">Export</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="bg-[#121212] border-border w-56">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Export all model stats</DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-border" />
        {!member && (
          <DropdownMenuItem asChild className="text-sm gap-2 cursor-pointer" data-testid="export-locked">
            <Link to="/join">
              <Lock className="h-4 w-4" /> Full exports are for members
            </Link>
          </DropdownMenuItem>
        )}
        {member && (<>
        <DropdownMenuItem data-testid="export-copy-md" onClick={copyMd} className="text-sm gap-2 cursor-pointer">
          <Copy className="h-4 w-4" /> Copy for Claude (markdown)
        </DropdownMenuItem>
        <DropdownMenuSeparator className="bg-border" />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Streaks by fixture (overs + unders)</DropdownMenuLabel>
        <DropdownMenuItem data-testid="export-streaks-7" onClick={() => copyStreaks(7)} className="text-sm gap-2 cursor-pointer">
          <Flame className="h-4 w-4" /> Copy this week's streaks
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="export-streaks-3" onClick={() => copyStreaks(3)} className="text-sm gap-2 cursor-pointer">
          <Flame className="h-4 w-4" /> Copy next 3 days
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="export-dl-md" onClick={dlMd} className="text-sm gap-2 cursor-pointer">
          <FileText className="h-4 w-4" /> Download .md
        </DropdownMenuItem>
        </>)}
        <DropdownMenuSeparator className="bg-border" />
        <DropdownMenuItem data-testid="export-csv-teams" onClick={() => dlCsv("teams")} className="text-sm gap-2 cursor-pointer">
          <Table className="h-4 w-4" /> Download teams CSV
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="export-csv-fixtures" onClick={() => dlCsv("fixtures")} className="text-sm gap-2 cursor-pointer">
          <Table className="h-4 w-4" /> Download fixtures CSV
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
