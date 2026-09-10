import { ArrowUpRight } from "lucide-react";
import { formatStipend, formatAge, isFresh, openApply, applyLabel } from "@/lib/format";

// The dense, scannable alternative to InternshipCard — a dateline row, not a tile.
// Used for the "ruled index" on Home and as the default view on the board.
export default function InternshipRow({ listing, onOpen }) {
  const fresh = isFresh(listing.hoursAgo);

  return (
    <div
      onClick={() => onOpen(listing)}
      className="group grid cursor-pointer grid-cols-[1fr_auto] items-center gap-4 border-b border-border py-4 transition-colors hover:bg-paper sm:grid-cols-[2fr_1fr_auto_auto]"
    >
      <div className="min-w-0">
        <h3 className="truncate font-display text-lg tracking-tight text-foreground sm:text-xl">
          {listing.title}
        </h3>
        <div className="mt-0.5 truncate text-sm text-muted-foreground">
          {listing.org} · {listing.location || "N/A"}
        </div>
      </div>

      <div className="hidden text-sm text-muted-foreground sm:block">
        <span className="uppercase tracking-wide">{listing.cluster}</span>
        <span className="mx-1.5 text-border">·</span>
        <span className="tabular-nums">{formatAge(listing.hoursAgo)}</span>
        {fresh && <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-accent-warm align-middle" />}
      </div>

      <div className="text-right text-sm font-semibold tabular-nums text-foreground">
        {formatStipend(listing.stipend)}
      </div>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          openApply(listing);
        }}
        className="hidden shrink-0 items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
      >
        {applyLabel(listing)}
        <ArrowUpRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
