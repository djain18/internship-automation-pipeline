import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";
import { isApprovedUser } from "@/lib/personalHunt";

// Internships is a real route (gets an active state); the other two are
// anchors on Home, so a plain Link with no active styling is honest here —
// NavLink would otherwise read "active" on every page that isn't /internships.
const anchorLinks = [
  { label: "How it works", to: "/#how-it-works" },
  { label: "FAQ", to: "/#faq" },
];

export default function Navbar() {
  const navigate = useNavigate();
  const { user, loading, signInWithGoogle, signOutUser } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const showMyHunt = isApprovedUser(user);

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 md:px-10 py-4 font-body">
        <Link to="/" aria-label="Rise, home" className="flex items-center">
          <img src="/rise-logo.png" alt="Rise" className="h-7 w-auto" />
        </Link>

        <div className="hidden md:flex items-center gap-8">
          <NavLink
            to="/internships"
            className={({ isActive }) =>
              `text-sm transition-colors ${
                isActive ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
              }`
            }
          >
            Internships
          </NavLink>
          {anchorLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
          {showMyHunt && (
            <NavLink
              to="/my-hunt"
              className={({ isActive }) =>
                `text-sm transition-colors ${
                  isActive ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                }`
              }
            >
              My hunt
            </NavLink>
          )}
        </div>

        <div className="flex items-center gap-3">
          {loading ? null : user ? (
            <div className="hidden items-center gap-3 md:flex">
              {user.photoURL && (
                <img
                  src={user.photoURL}
                  alt={user.displayName || user.email}
                  className="h-8 w-8 rounded-full"
                  referrerPolicy="no-referrer"
                />
              )}
              <button
                onClick={signOutUser}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Button
              onClick={() => navigate("/#alerts")}
              className="hidden rounded-full px-5 text-sm font-medium md:inline-flex"
            >
              Get daily alerts
            </Button>
          )}

          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            className="flex h-9 w-9 items-center justify-center rounded-full text-foreground md:hidden"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </nav>

      {menuOpen && (
        <div className="border-t border-border/60 bg-background px-6 py-4 font-body md:hidden">
          <div className="flex flex-col gap-4">
            <NavLink
              to="/internships"
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `text-sm ${isActive ? "font-medium text-foreground" : "text-muted-foreground"}`
              }
            >
              Internships
            </NavLink>
            {anchorLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setMenuOpen(false)}
                className="text-sm text-muted-foreground"
              >
                {link.label}
              </Link>
            ))}
            {showMyHunt && (
              <NavLink
                to="/my-hunt"
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `text-sm ${isActive ? "font-medium text-foreground" : "text-muted-foreground"}`
                }
              >
                My hunt
              </NavLink>
            )}
            {user ? (
              <button
                onClick={() => {
                  setMenuOpen(false);
                  signOutUser();
                }}
                className="text-left text-sm text-muted-foreground"
              >
                Sign out
              </button>
            ) : (
              <Button
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/#alerts");
                }}
                className="w-full rounded-full text-sm font-medium"
              >
                Get daily alerts
              </Button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
