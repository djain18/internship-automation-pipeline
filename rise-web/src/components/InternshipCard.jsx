import { MapPin, Clock, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatStipend, formatAge, isFresh, openApply, applyLabel } from "@/lib/format";

export default function InternshipCard({ listing, onOpen, featured = false }) {
  const fresh = isFresh(listing.hoursAgo);

  return (
    <div
      onClick={() => onOpen(listing)}
      className="group flex h-full cursor-pointer flex-col border border-border bg-background p-5 transition-colors duration-200 hover:border-foreground/40 hover:bg-paper"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{listing.org}</div>
          <h3
            className={`mt-0.5 font-display leading-tight tracking-tight text-foreground ${
              featured ? "text-3xl md:text-4xl" : "text-2xl"
            }`}
          >
            {listing.title}
          </h3>
        </div>
        <span className="shrink-0 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {listing.cluster}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <MapPin className="h-3.5 w-3.5" />
          {listing.location || "—"}
        </span>
        <span>{listing.type}</span>
        <span className="inline-flex items-center gap-1 tabular-nums">
          <Clock className="h-3.5 w-3.5" />
          {formatAge(listing.hoursAgo)}
        </span>
        {fresh && (
          <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-warm" />
            Fresh
          </span>
        )}
      </div>

      {listing.tags?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {listing.tags.slice(0, 4).map((t, i) => (
            <span key={t}>
              {i > 0 && <span className="mr-3 text-border">·</span>}
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-end justify-between pt-5">
        <div
          className={`font-semibold tabular-nums text-foreground ${
            featured ? "text-xl" : "text-base"
          }`}
        >
          {formatStipend(listing.stipend)}
        </div>
        <Button
          variant="outline"
          onClick={(e) => {
            e.stopPropagation();
            openApply(listing);
          }}
          className="rounded-full px-4 text-xs font-medium"
        >
          {applyLabel(listing)}
          <ArrowUpRight className="ml-1 h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
