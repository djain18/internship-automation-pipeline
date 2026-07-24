import { useState } from "react";
import { ChevronDown } from "lucide-react";
import Reveal from "./Reveal";

const ITEMS = [
  {
    q: "Is Rise genuinely free?",
    a: "Yes — free for students, and intended to stay that way. We don't charge readers and we don't sell your email address.",
  },
  {
    q: "How are the scams kept out?",
    a: "A language model reads every posted internship and spikes registration fees, “earn ₹X a day” schemes, typing jobs, posts with no apply link, and roles that aren't open to students in India. Edge cases are checked by hand.",
  },
  {
    q: "Is it only for engineers?",
    a: "No. The board carries Design, Marketing, Finance, HR, Content, Product, Business Development, Legal and Operations alongside Software. Every field gets its own feed.",
  },
  {
    q: "How fresh are the listings?",
    a: "Every role is pulled from posts made in the last 24 hours and republished each night. Stale listings drop off the board automatically, so what you see is current.",
  },
  {
    q: "What arrives in the daily email?",
    a: "One short email: the freshest, highest-graded roles matched to the fields and cities you pick. No digest, no advertising — and one click unsubscribes, any time.",
  },
  {
    q: "How do I actually apply?",
    a: "Every listing links straight to the source — the company's apply link, the original post, or the recruiter's email. You apply directly with them; Rise never sits in between.",
  },
];

function Item({ item, open, onToggle }) {
  return (
    <div className="border-b border-border">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-6 py-6 text-left"
      >
        <span className="text-base font-medium text-foreground sm:text-lg">{item.q}</span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      <div
        className={`grid transition-all duration-300 ${
          open ? "grid-rows-[1fr] pb-6 opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">{item.a}</p>
        </div>
      </div>
    </div>
  );
}

export default function FAQ() {
  const [open, setOpen] = useState(0);

  return (
    <section id="faq" className="scroll-mt-20 border-t border-border">
      <div className="mx-auto max-w-5xl px-6 py-20 md:px-10">
        <div className="md:grid md:grid-cols-[240px_1fr] md:gap-16">
          <Reveal>
            <span className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
              Need to know
            </span>
            <h2 className="mt-3 font-display text-4xl tracking-tight text-foreground md:sticky md:top-24">
              Questions, answered
            </h2>
          </Reveal>

          <Reveal delay={0.1} className="mt-10 border-t border-border md:mt-0 md:border-t-0">
            {ITEMS.map((item, i) => (
              <Item
                key={item.q}
                item={item}
                open={open === i}
                onToggle={() => setOpen(open === i ? -1 : i)}
              />
            ))}
          </Reveal>
        </div>
      </div>
    </section>
  );
}
