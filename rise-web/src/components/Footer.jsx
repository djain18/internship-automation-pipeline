import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-6xl px-6 py-12 md:px-10">
        <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Link to="/" aria-label="Rise — home" className="inline-flex">
              <img src="/rise-logo.png" alt="Rise" className="h-7 w-auto" />
            </Link>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Real internships for students in India — scraped, scam-filtered and verified
              every night. Free to use, always.
            </p>
          </div>

          <div className="flex gap-12 text-sm">
            <div className="space-y-2">
              <div className="font-medium text-foreground">Explore</div>
              <Link to="/internships" className="block text-muted-foreground hover:text-foreground">
                Internships
              </Link>
              <Link to="/how-it-works" className="block text-muted-foreground hover:text-foreground">
                How it works
              </Link>
              <Link to="/faq" className="block text-muted-foreground hover:text-foreground">
                FAQ
              </Link>
            </div>
            <div className="space-y-2">
              <div className="font-medium text-foreground">Stay in touch</div>
              <Link to="/#alerts" className="block text-muted-foreground hover:text-foreground">
                Daily alerts
              </Link>
            </div>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-2 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>© {new Date().getFullYear()} Rise. Free for students.</span>
          <span>Rise never charges to apply. A real internship never asks for a fee.</span>
        </div>
      </div>
    </footer>
  );
}
