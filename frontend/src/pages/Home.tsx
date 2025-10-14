import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div style={{ maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui" }}>
      <h1>DFSP</h1>
      <p>Decentralized File Sharing Platform — dev UI</p>

      <nav style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginTop: 16 }}>
        <Link to="/health">Health</Link>
        <Link to="/register">Register</Link>
        <Link to="/login">Login</Link>
        <Link to="/upload">Upload</Link>
        <Link to="/files">Files</Link>
        <Link to="/verify">Verify</Link>
      </nav>

      <section style={{ marginTop: 24, fontSize: 14, opacity: 0.8 }}>
        <div>API: {import.meta.env.VITE_API_BASE ?? "http://localhost:8000"}</div>
        <div>IPFS gateway: {import.meta.env.VITE_IPFS_PUBLIC_GATEWAY ?? "http://localhost:8080"}</div>
        <div>Chain ID: {import.meta.env.VITE_CHAIN_ID ?? "31337"}</div>
      </section>
    </div>
  );
}
