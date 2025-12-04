
import "./polyfills";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { initOfflineQueue } from "./lib/offlineQueue";

createRoot(document.getElementById("root")!).render(<App />);
initOfflineQueue();
  
