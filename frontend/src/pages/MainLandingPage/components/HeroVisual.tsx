import {ArrowRight, Github, Sparkles} from "lucide-react";
import { Button } from "../../../components/ui/button";
import dfspLogo from "../../../assets/dfsp-logo.png";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../components/useAuth";

export function HeroVisual() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const handleLaunchClick = () => {
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
      {/* Animated background gradient blobs */}
      <div className="absolute inset-0">
        <div className="absolute top-0 left-1/4 h-[500px] w-[500px] rounded-full bg-cyan-500/10 blur-3xl animate-blob" />
        <div className="absolute bottom-0 right-1/4 h-[500px] w-[500px] rounded-full bg-fuchsia-500/10 blur-3xl animate-blob animation-delay-2000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[400px] w-[400px] rounded-full bg-purple-500/5 blur-3xl animate-blob animation-delay-4000" />
      </div>

      <div className="relative mx-auto max-w-7xl px-6 py-16 sm:py-24 lg:px-8">
        {/* Status badge */}
        <div className="flex justify-center mb-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-4 py-2 backdrop-blur-sm">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            <span className="text-sm text-cyan-300">Fully Decentralized & Encrypted</span>
          </div>
        </div>

        {/* Logo with glow effect */}
        <div className="flex justify-center mb-8">
          <div className="relative">
            <div className="absolute inset-0 blur-2xl opacity-30">
              <img src={dfspLogo} alt="" className="h-48 w-48 sm:h-64 sm:w-64" />
            </div>
            <img src={dfspLogo} alt="DFSP Logo" className="relative h-48 w-48 sm:h-64 sm:w-64" />
          </div>
        </div>

        {/* Title and description */}
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="mb-6 bg-gradient-to-br from-cyan-300 via-zinc-100 to-fuchsia-300 bg-clip-text text-transparent">
            DFSP
          </h1>

          <div className="mb-4 flex justify-center">
            <div className="inline-block rounded-lg border border-zinc-700 bg-zinc-900/50 px-6 py-2 backdrop-blur-sm">
              <p className="text-xl tracking-wide text-zinc-300">
                Decentralized File Sharing Protocol
              </p>
            </div>
          </div>

          <p className="mb-10 text-lg text-zinc-400 max-w-2xl mx-auto">
            Secure, gasless, user-friendly file sharing on top of
            <span className="text-cyan-400"> IPFS </span>
            +
            <span className="text-fuchsia-400"> EVM </span>
            smart contracts. Files are encrypted client-side with on-chain
            authenticity and access control.
          </p>

          <div className="flex flex-wrap justify-center gap-4 mb-16">
            <Button
              size="lg"
              className="group bg-gradient-to-r from-cyan-600 to-fuchsia-600 hover:from-cyan-700 hover:to-fuchsia-700"
              onClick={handleLaunchClick}
            >
              Get Started
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
                View on Github
              </Button>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
