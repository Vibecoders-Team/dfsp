import "./polyfills";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { initOfflineQueue } from "./lib/offlineQueue";
// Lightweight loader: listens for WalletConnect events and lazy-loads the portal only when needed
import './components/WalletConnectLoader';

createRoot(document.getElementById("root")!).render(<App />);
initOfflineQueue();
