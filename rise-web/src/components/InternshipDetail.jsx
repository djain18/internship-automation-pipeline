import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, MapPin, Clock, Calendar, Briefcase, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatStipend, formatAge, openApply, applyLabel } from "@/lib/format";

function Meta({ icon: Icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-sm font-medium text-foreground">{value}</div>
      </div>
    </div>
  );
}

export default function InternshipDetail({ listing, onClose }) {
  useEffect(() => {
    if (!listing) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [listing, onClose]);

  return (
    <AnimatePresence>
      {listing && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-end justify-center bg-foreground/30 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-3xl bg-background p-6 shadow-dashboard sm:rounded-3xl md:p-8"
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            transition={{ type: "spring", damping: 26, stiffness: 280 }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={onClose}
              className="absolute right-5 top-5 rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="pr-8">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>{listing.org}</span>
                <span className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[11px] text-secondary-foreground">
                  {listing.cluster}
                </span>
              </div>
              <h2 className="mt-1 font-display text-3xl tracking-tight text-foreground md:text-4xl">
                {listing.title}
              </h2>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-4 rounded-2xl border border-border bg-secondary/30 p-4 sm:grid-cols-3">
              <Meta icon={MapPin} label="Location" value={`${listing.location} · ${listing.type}`} />
              <Meta icon={Briefcase} label="Stipend" value={formatStipend(listing.stipend)} />
              <Meta icon={Clock} label="Commitment" value={`${listing.timing}${listing.duration ? " · " + listing.duration : ""}`} />
              <Meta icon={Calendar} label="Apply by" value={listing.deadline} />
              <Meta icon={Briefcase} label="Experience" value={listing.experience} />
              <Meta icon={Clock} label="Posted" value={formatAge(listing.hoursAgo)} />
            </div>

            {listing.desc && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold text-foreground">About the role</h3>
                <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
                  {listing.desc}
                </p>
              </div>
            )}

            {listing.tags?.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-1.5">
                {listing.tags.map((t) => (
                  <span
                    key={t}
                    className="rounded-md bg-secondary px-2.5 py-1 text-xs text-muted-foreground"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button
                onClick={() => openApply(listing)}
                className="rounded-full px-6 py-5 text-sm font-medium"
              >
                {applyLabel(listing)}
                <ExternalLink className="ml-1.5 h-4 w-4" />
              </Button>
              {listing.postUrl && (
                <a
                  href={listing.postUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  View the original post
                </a>
              )}
            </div>
            <p className="mt-4 text-xs text-muted-foreground">
              Rise never charges to apply. If a role asks for a fee, it isn't real — report it.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
