import { tierLabel, tierTitle, tierClass } from "@/lib/tier";

// The division marker that sits beside a team on any cross-league board.
//
// Renders NOTHING when the tier is unknown rather than guessing or printing a dash: a
// blank says "not stated", where a "T?" would read as a real category and a dash would
// read as tier zero.
export default function TierBadge({ tier, country = "", className = "" }) {
  const label = tierLabel(tier);
  if (!label) return null;
  return (
    <span
      data-testid="tier-badge"
      title={tierTitle(tier, country)}
      className={`shrink-0 inline-flex items-center rounded border px-1 text-[9px] font-mono-data
                  leading-[1.4] ${tierClass(tier)} ${className}`}
    >
      {label}
    </span>
  );
}
