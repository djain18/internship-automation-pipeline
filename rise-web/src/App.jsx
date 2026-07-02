import { useEffect, useState } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ScrollProgress from "./components/ScrollProgress";
import Dashboard from "./components/Dashboard";
import InternshipDetail from "./components/InternshipDetail";
import Home from "./pages/Home";
import Internships from "./pages/Internships";
import HowItWorksPage from "./pages/HowItWorksPage";
import FAQPage from "./pages/FAQPage";
import { fetchListings, fetchStats } from "./lib/api";

// On route change: scroll to top, or to the hashed section if a #hash is present.
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      // Wait a tick for the target section to render, then scroll to it.
      const id = hash.replace("#", "");
      requestAnimationFrame(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } else {
      window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
    }
  }, [pathname, hash]);
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
      <ScrollManager />
      <Navbar />
      <main>
        <Routes>
          <Route path="/" element={<Home {...shared} />} />
          <Route path="/internships" element={<Internships {...shared} />} />
          <Route path="/how-it-works" element={<HowItWorksPage stats={stats} />} />
          <Route path="/faq" element={<FAQPage />} />
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
