import { useEffect, useState } from "react";

type State = { status: "idle"|"loading"|"ok"|"error", data?: unknown };

export default function HealthPage(){
  const [s, setS] = useState<State>({ status: "idle" });

  useEffect(() => {
    (async () => {
      setS({ status: "loading" });
      try {
        const api = import.meta.env.VITE_API_URL || 'http://localhost:3001';
        const res = await fetch(`${api}/health`);
        if(!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setS({ status: "ok", data: json });
      } catch(e) {
        setS({ status: "error", data: { message: (e as Error).message } });
      }
    })();
  }, []);

  return (
    <main>
      <h1>/health</h1>
      <p>Status: {s.status}</p>
      <pre>{JSON.stringify(s.data ?? {}, null, 2)}</pre>
    </main>
  );
}