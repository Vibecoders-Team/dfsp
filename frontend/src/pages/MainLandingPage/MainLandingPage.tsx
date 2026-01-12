import { HeroVisual } from "./components/HeroVisual";
import { StatsSection } from "./components/StatsSection";
import { FeaturesVisual } from "./components/FeaturesVisual";
import { CTASection } from "./components/CTASection";
import { Footer } from "./components/Footer";
import { useEffect } from "react";

export function MainLandingPage() {
  useEffect(() => {
    // Load a dedicated CSS with full set of utilities/variables for the landing page
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/landing.css";
    link.dataset.dfspLanding = "true";
    document.head.appendChild(link);
    return () => {
      // Remove on page exit so other screens are unaffected
      const el = document.querySelector('link[data-dfsp-landing="true"]');
      el?.parentElement?.removeChild(el);
    };
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <HeroVisual />
      <StatsSection />
      <FeaturesVisual />
      <CTASection />
      <Footer />
    </div>
  );
}
