import { MapPin, Clock, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatStipend, formatAge, isFresh, openApply, applyLabel } from "@/lib/format";

export default function InternshipCard({ listing, onOpen }) {
  const fresh = isFresh(listing.hoursAgo);

  return (
    <div
      onClick={() => onOpen(listing)}
      className="group flex h-full cursor-pointer flex-col rounded-2xl border border-border bg-background p-5 transition-all hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-[0_12px_40px_-12px_rgba(0,0,0,0.12)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{listing.org}</div>
          <h3 className="mt-0.5 font-display text-2xl leading-tight tracking-tight text-foreground">
            {listing.title}
          </h3>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-secondary px-2.5 py-1 text-[11px] font-medium text-secondary-foreground">
          {listing.cluster}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <MapPin className="h-3.5 w-3.5" />
          {listing.location || "—"}
        </span>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">{listing.type}</span>
        <span className="inline-flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" />
          {formatAge(listing.hoursAgo)}
        </span>
      </div>

      {listing.tags?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {listing.tags.slice(0, 4).map((t) => (
            <span
              key={t}
              className="rounded-md bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-end justify-between pt-5">
        <div>
          <div className="text-base font-semibold text-foreground">
            {formatStipend(listing.stipend)}
          </div>
          {fresh && (
            <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] font-medium text-green-600">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
              Fresh
            </div>
          )}
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
