import { useState } from "react";
import { fetchCid, fetchMeta, fetchVersions, fetchHistory } from "../lib/api";

export default function Files() {
  const [idHex, setIdHex] = useState("");
  const [cid, setCid] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [versions, setVersions] = useState<any>(null);
  const [history, setHistory] = useState<any>(null);
  const [err, setErr] = useState("");

  async function onResolve() {
    setErr(""); setCid(null);
    try { setCid(await fetchCid(idHex)); } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Resolve failed");
    }
  }
  async function onMeta() {
    setErr(""); setMeta(null);
    try { setMeta(await fetchMeta(idHex)); } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Meta failed");
    }
  }
  async function onVersions() {
    setErr(""); setVersions(null);
    try { setVersions(await fetchVersions(idHex)); } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Versions failed");
    }
  }
  async function onHistory() {
    setErr(""); setHistory(null);
    try { setHistory(await fetchHistory(idHex)); } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "History failed");
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "2rem auto", fontFamily: "Inter, system-ui" }}>
      <h2>Files</h2>
      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "1fr auto", alignItems: "center" }}>
        <input placeholder="id_hex (0x + 64)" value={idHex} onChange={(e) => setIdHex(e.target.value)} />
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onResolve}>CID</button>
          <button onClick={onMeta}>Meta</button>
          <button onClick={onVersions}>Versions</button>
          <button onClick={onHistory}>History</button>
        </div>
      </div>
      {err && <p style={{ color: "crimson" }}>{err}</p>}
      {cid && (<><h3>CID</h3><pre>{JSON.stringify(cid, null, 2)}</pre>{cid.url && <a href={cid.url} target="_blank" rel="noreferrer">Open</a>}</>)}
      {meta && (<><h3>Meta</h3><pre>{JSON.stringify(meta, null, 2)}</pre></>)}
      {versions && (<><h3>Versions</h3><pre>{JSON.stringify(versions, null, 2)}</pre></>)}
      {history && (<><h3>History</h3><pre>{JSON.stringify(history, null, 2)}</pre></>)}
    </div>
  );
}
