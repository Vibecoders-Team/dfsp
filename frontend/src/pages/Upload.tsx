// src/pages/Upload.tsx
import { useState } from "react";
import { storeFile, fetchMeta, fetchVersions, fetchHistory } from "../lib/api";

export default function Upload() {
  const [file, setFile] = useState<File| null>(null);
  const [idHex, setIdHex] = useState("");
  const [out, setOut] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [versions, setVersions] = useState<any>(null);
  const [history, setHistory] = useState<any>(null);
  const [err, setErr] = useState("");

  async function onUpload() {
    setErr("");
    if (!file) return setErr("Pick a file");
    try {
      const res = await storeFile(file, idHex || undefined);
      setOut(res);
      const [m, v, h] = await Promise.all([
        fetchMeta(res.id_hex),
        fetchVersions(res.id_hex),
        fetchHistory(res.id_hex),
      ]);
      setMeta(m); setVersions(v); setHistory(h);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Upload failed");
    }
  }

  return (
    <div className="container">
      <h2>Upload</h2>
      <input type="file" onChange={(e)=>setFile(e.target.files?.[0]||null)} />
      <input placeholder="optional id_hex (0x + 64)" value={idHex} onChange={(e)=>setIdHex(e.target.value)} />
      <button onClick={onUpload}>Store</button>
      {err && <p style={{color:"crimson"}}>{err}</p>}
      {out && (<>
        <pre>{JSON.stringify(out,null,2)}</pre>
        <a href={out.url} target="_blank">Open in IPFS</a>
      </>)}
      {meta && (<><h3>Meta</h3><pre>{JSON.stringify(meta,null,2)}</pre></>)}
      {versions && (<><h3>Versions</h3><pre>{JSON.stringify(versions,null,2)}</pre></>)}
      {history && (<><h3>History</h3><pre>{JSON.stringify(history,null,2)}</pre></>)}
    </div>
  );
}
