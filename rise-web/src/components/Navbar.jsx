import { Link, NavLink, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/AuthContext";

const links = [
  { label: "Internships", to: "/internships" },
  { label: "How it works", to: "/how-it-works" },
  { label: "FAQ", to: "/faq" },
];

export default function Navbar() {
  const navigate = useNavigate();
  const { user, loading, signInWithGoogle, signOutUser } = useAuth();

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 md:px-10 py-4 font-body">
        <Link to="/" aria-label="Rise — home" className="flex items-center">
          <img src="/rise-logo.png" alt="Rise" className="h-7 w-auto" />
        </Link>

        <div className="hidden md:flex items-center gap-8">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `text-sm transition-colors ${
                  isActive ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </div>

        {loading ? null : user ? (
          <div className="flex items-center gap-3">
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
            className="rounded-full px-5 text-sm font-medium"
          >
            Get daily alerts
          </Button>
        )}
      </nav>
    </header>
  );
}
