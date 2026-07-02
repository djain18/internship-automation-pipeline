import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import StatDashboard from "./StatDashboard";

const VIDEO_URL =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260319_015952_e1deeb12-8fb7-4071-a42a-60779fc64ab6.mp4";

export default function Hero({ stats, listings = [], onOpenDashboard }) {
  const verified = stats?.verifiedToday ?? listings.length;
  const navigate = useNavigate();

  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const videoScale = useTransform(scrollYProgress, [0, 1], [1, 1.18]);
  const panelY = useTransform(scrollYProgress, [0, 1], [0, 90]);
  const contentY = useTransform(scrollYProgress, [0, 1], [0, -40]);
  const contentOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0.2]);

  return (
    <section ref={ref} className="relative overflow-hidden">
      {/* Background video */}
      <motion.video
        style={{ scale: videoScale }}
        className="absolute inset-0 z-0 h-full w-full object-cover"
        src={VIDEO_URL}
        autoPlay
        muted
        loop
        playsInline
      />
      {/* Soft wash so text stays readable over the video */}
      <div className="absolute inset-0 z-0 bg-gradient-to-b from-background/40 via-background/10 to-background" />

      {/* Content */}
      <div className="relative z-10 flex w-full flex-col items-center px-6 pt-12 pb-16">
        <motion.div
          style={{ y: contentY, opacity: contentOpacity }}
          className="flex flex-col items-center"
        >
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-6 inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-4 py-1.5 text-sm text-muted-foreground font-body"
        >
          Updated nightly · {verified} new internships tonight ✨
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="max-w-2xl text-center font-display text-5xl md:text-6xl lg:text-[5rem] leading-[0.95] tracking-tight text-foreground"
        >
          The internships worth your time, <em className="italic">verified</em> every night
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mt-4 max-w-[650px] text-center text-base md:text-lg text-muted-foreground leading-relaxed font-body"
        >
          Every night we read every internship posted across LinkedIn, throw out the
          scams and the roles you can't apply to, and publish only the real, fresh,
          India-eligible ones—so you stop scrolling and start applying.
        </motion.p>

        {/* CTA buttons */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-6 flex items-center gap-3"
        >
          <Button
            onClick={() => navigate("/internships")}
            className="rounded-full px-6 py-5 text-sm font-medium font-body"
          >
            Browse internships
            <ArrowRight className="ml-1.5 h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            onClick={() => navigate("/#alerts")}
            className="rounded-full border border-border bg-background px-5 py-5 text-sm font-medium font-body shadow-[0_2px_12px_rgba(0,0,0,0.08)] hover:bg-background/80"
          >
            <Bell className="mr-1.5 h-4 w-4" />
            Get daily alerts
          </Button>
        </motion.div>
        </motion.div>

        {/* Stat dashboard preview */}
        <motion.div
          style={{ y: panelY }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.5 }}
          className="mt-10 w-full max-w-5xl"
        >
          <button
            type="button"
            onClick={onOpenDashboard}
            aria-label="Open the live dashboard"
            className="group relative block w-full cursor-pointer rounded-2xl p-3 text-left transition-transform duration-300 hover:-translate-y-1 md:p-4"
            style={{
              background: "rgba(255, 255, 255, 0.4)",
              border: "1px solid rgba(255, 255, 255, 0.5)",
              boxShadow: "var(--shadow-dashboard)",
            }}
          >
            <StatDashboard stats={stats} listings={listings} />
            {/* Hover affordance: hint this preview is interactive */}
            <span className="pointer-events-none absolute right-5 top-5 z-10 inline-flex items-center gap-1.5 rounded-full bg-foreground px-3 py-1.5 text-xs font-medium text-background opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
              Open live dashboard
              <ArrowRight className="h-3.5 w-3.5" />
            </span>
          </button>
        </motion.div>
      </div>
    </section>
  );
}
