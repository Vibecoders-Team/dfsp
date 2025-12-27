import { Github, Twitter, FileText } from "lucide-react";
import dfspLogo from "../../../assets/dfsp-logo.png";

export function Footer() {
  return (
    <footer className="bg-zinc-950">
      <div className="mx-auto max-w-7xl px-6 py-12 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <div className="mb-4 flex items-center gap-3">
              <img src={dfspLogo} alt="DFSP" className="h-10 w-10" />
              <span className="text-xl tracking-tight">DFSP</span>
            </div>
            <p className="mb-4 max-w-md text-sm text-zinc-400">
              Decentralized file sharing with end-to-end encryption. Security,
              privacy and control in your hands.
            </p>
            <div className="flex gap-4">
              <a
                href="https://github.com/Vibecoders-Team/dfsp"
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 hover:text-zinc-300 transition-colors"
              >
                <Github className="h-5 w-5" />
              </a>
              <a
                href="#"
                className="text-zinc-400 hover:text-zinc-300 transition-colors"
              >
                <Twitter className="h-5 w-5" />
              </a>
              <a
                href="https://github.com/Vibecoders-Team/dfsp"
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 hover:text-zinc-300 transition-colors"
              >
                <FileText className="h-5 w-5" />
              </a>
            </div>
          </div>

          <div>
            <h4 className="mb-4 text-sm text-zinc-100">Product</h4>
            <ul className="space-y-3 text-sm">
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Features
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Security
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Documentation
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  API
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="mb-4 text-sm text-zinc-100">About</h4>
            <ul className="space-y-3 text-sm">
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  About Us
                </a>
              </li>
              <li>
                <a
                  href="#"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Open Source
                </a>
              </li>
              <li>
                <a
                  href="/privacy"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Privacy Policy
                </a>
              </li>
              <li>
                <a
                  href="/terms"
                  className="text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Terms of Service
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 border-t border-zinc-800 pt-8 text-center text-sm text-zinc-400">
          <p>© 2025 DFSP. Fully decentralized and open source.</p>
        </div>
      </div>
    </footer>
  );
}
