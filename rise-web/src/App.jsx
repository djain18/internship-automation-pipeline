import { lazy, Suspense, useEffect, useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ScrollProgress from "./components/ScrollProgress";
import Dashboard from "./components/Dashboard";
import InternshipDetail from "./components/InternshipDetail";
import Home from "./pages/Home";
import Internships from "./pages/Internships";
import { fetchListings, fetchStats } from "./lib/api";

const MyHunt = lazy(() => import("./pages/MyHunt"));
const Outbox = lazy(() => import("./pages/Outbox"));

// On route change: scroll to top, or to the hashed section if a #hash is present.
function ScrollManager({ ready }) {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const id = hash.replace("#", "");
      const attempt = () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      // Sections above the target (e.g. the async listings teaser) can still be
      // in their short "loading" state on the first attempt, changing height once
      // data arrives — retry briefly so the scroll lands correctly either way.
      requestAnimationFrame(attempt);
      const t1 = setTimeout(attempt, 300);
      const t2 = setTimeout(attempt, 900);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    } else {
      window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
    }
  }, [pathname, hash, ready]);
  return null;
}

export default function App() {
  const [listings, setListings] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [dashboardOpen, setDashboardOpen] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([fetchListings(ctrl.signal), fetchStats(ctrl.signal)])
      .then(([l, s]) => {
        setListings(l);
        setStats(s);
        setLoading(false);
      })
      .catch(() => {
        // Aborted by cleanup (StrictMode/unmount) — the surviving run sets state.
      });
    return () => ctrl.abort();
  }, []);

  const shared = {
    listings,
    stats,
    loading,
    onOpen: setSelected,
    onOpenDashboard: () => setDashboardOpen(true),
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <ScrollProgress />
      <ScrollManager ready={!loading} />
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Home {...shared} />} />
          <Route path="/internships" element={<Internships {...shared} />} />
          <Route
            path="/my-hunt"
            element={
              <Suspense fallback={<div className="min-h-[60vh] bg-secondary/30" />}>
                <MyHunt />
              </Suspense>
            }
          />
          <Route
            path="/my-hunt/outbox"
            element={
              <Suspense fallback={<div className="min-h-[60vh] bg-secondary/30" />}>
                <Outbox />
              </Suspense>
            }
          />
          {/* How-it-works and FAQ are sections on Home now, not standalone pages —
              old links still work by redirecting to the anchor. */}
          <Route path="/how-it-works" element={<Navigate to="/#how-it-works" replace />} />
          <Route path="/faq" element={<Navigate to="/#faq" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
      <Dashboard
        open={dashboardOpen}
        onClose={() => setDashboardOpen(false)}
        stats={stats}
        listings={listings}
        onOpenListing={setSelected}
      />
      <InternshipDetail listing={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
