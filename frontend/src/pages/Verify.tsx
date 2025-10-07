import { useState } from "react";
import { fetchMeta } from "../lib/api";
import { keccak256 } from "ethers";

function ab2u8(buf: ArrayBuffer) { return new Uint8Array(buf); }
async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2,"0")).join("");
}
function keccakHex(buf: ArrayBuffer): string {
  const hex = keccak256(ab2u8(buf)); // "0x..."
  return hex.slice(2);
}

export default function Verify() {
  const [file, setFile] = useState<File | null>(null);
  const [idHex, setIdHex] = useState("");
  const [meta, setMeta] = useState<any>(null);
  const [sha256, setSha256] = useState("");
  const [keccak, setKeccak] = useState("");
  const [match, setMatch] = useState<boolean | null>(null);
  const [err, setErr] = useState("");

  async function onVerify() {
    setErr(""); setMatch(null);
    if (!file) return setErr("Pick a file");
    if (!idHex) return setErr("Provide id_hex");
    try {
      const buf = await file.arrayBuffer();
      const s1 = await sha256Hex(buf);
      const s2 = keccakHex(buf);
      setSha256(s1); setKeccak(s2);
      const m = await fetchMeta(idHex);
      setMeta(m);
      setMatch((m?.checksum ?? "").toLowerCase() === s2.toLowerCase());
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Verify failed");
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui" }}>
      <h2>Verify</h2>
      <div style={{ display: "grid", gap: 8 }}>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <input placeholder="id_hex (0x + 64)" value={idHex} onChange={(e) => setIdHex(e.target.value)} />
        <button onClick={onVerify}>Verify</button>
      </div>
      {err && <p style={{ color: "crimson" }}>{err}</p>}
      {meta && (<><h3>On-chain</h3><pre>{JSON.stringify(meta, null, 2)}</pre></>)}
      {(sha256 || keccak) && (<><h3>Local</h3><pre>{JSON.stringify({ sha256, keccak }, null, 2)}</pre></>)}
      {match !== null && <p style={{ fontWeight: 600, color: match ? "green" : "crimson" }}>{match ? "MATCH" : "MISMATCH"}</p>}
    </div>
  );
}
