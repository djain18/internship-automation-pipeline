import { useState } from "react";
import { Plus } from "lucide-react";
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
        className="flex w-full items-center justify-between gap-4 py-5 text-left"
      >
        <span className="text-base font-medium text-foreground">{item.q}</span>
        <Plus
          className={`h-5 w-5 shrink-0 text-muted-foreground transition-transform duration-300 ${
            open ? "rotate-45" : ""
          }`}
        />
      </button>
      <div
        className={`grid transition-all duration-300 ${
          open ? "grid-rows-[1fr] pb-5 opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden">
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{item.a}</p>
        </div>
      </div>
    </div>
  );
}

export default function FAQ() {
  const [open, setOpen] = useState(0);

  return (
    <section id="faq" className="scroll-mt-20 border-t border-border">
      <div className="mx-auto max-w-3xl px-6 py-20 md:px-10">
        <Reveal>
          <h2 className="font-display text-4xl tracking-tight text-foreground md:text-5xl">
            Questions, answered
          </h2>
        </Reveal>
        <div className="mt-8">
          {ITEMS.map((item, i) => (
            <Reveal key={item.q} delay={i * 0.05}>
              <Item
                item={item}
                open={open === i}
                onToggle={() => setOpen(open === i ? -1 : i)}
              />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
