import { useEffect, useState } from 'react';

type Conn = { effectiveType?: string; saveData?: boolean; addEventListener?: (ev: string, cb: () => void) => void; removeEventListener?: (ev: string, cb: () => void) => void; onchange?: () => void };

export function useConnectionSpeed() {
  const [effectiveType, setEffectiveType] = useState<string | null>(null);
  const [saveData, setSaveData] = useState(false);

  useEffect(() => {
    const conn: Conn | undefined = (navigator as { connection?: Conn }).connection;
    if (!conn) return;
    const update = () => {
      setEffectiveType(conn.effectiveType || null);
      setSaveData(!!conn.saveData);
    };
    update();
    if (conn.addEventListener) {
      conn.addEventListener('change', update);
      return () => conn.removeEventListener?.('change', update);
    }
    if (typeof conn.onchange === 'function') {
      const prev = conn.onchange;
      conn.onchange = () => { prev?.(); update(); };
      return () => { conn.onchange = prev; };
    }
  }, []);

  const isSlowConnection = saveData || effectiveType === 'slow-2g' || effectiveType === '2g' || effectiveType === '3g';
  return { isSlowConnection, effectiveType, saveData };
}
