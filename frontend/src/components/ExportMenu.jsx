import { useState } from "react";
import { toast } from "sonner";
import { Download, Copy, FileText, Table, Loader2, Flame } from "lucide-react";
import { api } from "@/lib/api";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function download(text, filename, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportMenu() {
  const [busy, setBusy] = useState(false);

  const run = async (fn) => {
    setBusy(true);
    try { await fn(); } catch { toast.error("Export failed"); }
    finally { setBusy(false); }
  };

  const copyMd = () => run(async () => {
    const md = await api.exportMarkdown();
    await navigator.clipboard.writeText(md);
    toast.success("All stats copied — paste into Claude");
  });
  const copyStreaks = (days) => run(async () => {
    const md = await api.exportStreaks(days);
    await navigator.clipboard.writeText(md);
    toast.success(`Next ${days} days of streaks copied — paste into Claude`);
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
