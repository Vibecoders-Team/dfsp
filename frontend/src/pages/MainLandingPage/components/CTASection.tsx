import { Button } from "../../../components/ui/button";
import { ArrowRight, Github } from "lucide-react";
import dfspLogo from "../../../assets/dfsp-logo.png";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../components/useAuth";

export function CTASection() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const handleLaunchClick = () => {
    // Новая логика: три ветки
    if (isAuthenticated) {
      navigate("/files");
      return;
    }
    try {
      const hasAddress = !!localStorage.getItem("dfsp_address");
      navigate(hasAddress ? "/login" : "/register");
    } catch {
      navigate("/login");
    }
  };

  return (
    <div className="relative overflow-hidden border-b border-zinc-800">
      {/* Gradient background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-cyan-950/30 via-zinc-950 to-fuchsia-950/30" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] rounded-full bg-gradient-to-r from-cyan-500/10 to-fuchsia-500/10 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 py-24 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          {/* Logo */}
          <div className="mb-8 flex justify-center">
            <img src={dfspLogo} alt="DFSP" className="h-32 w-32 opacity-80" />
          </div>

          <h2 className="mb-4 bg-gradient-to-br from-zinc-100 to-zinc-400 bg-clip-text text-transparent">
            Ready to share files securely?
          </h2>

          <p className="mb-10 text-lg text-zinc-400">
            Join the decentralized file sharing revolution. No signup required,
            no credit card needed. Start sharing in seconds.
          </p>

          <div className="flex flex-wrap justify-center gap-4">
            <Button
              size="lg"
              className="group bg-gradient-to-r from-cyan-600 to-fuchsia-600 hover:from-cyan-700 hover:to-fuchsia-700"
              onClick={handleLaunchClick}
            >
              Launch App
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Button>
            <a
              href="https://github.com/Vibecoders-Team/dfsp"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex"
            >
              <Button
                size="lg"
                variant="outline"
                className="border-zinc-700 bg-zinc-900/50 backdrop-blur-sm hover:bg-zinc-800 text-white"
              >
                <Github className="mr-2 h-4 w-4" />
                View on GitHub
              </Button>
            </a>
          </div>

          {/* Additional info */}
          <div className="mt-12 flex flex-wrap justify-center gap-6 text-sm text-zinc-500">
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
              <span>Open Source</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-cyan-500" />
              <span>MIT Licensed</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-fuchsia-500" />
              <span>Self-Hostable</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
