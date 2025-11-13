// src/lib/pubkeys.ts
export type ContactKey = { address: string; pem: string; addedAt: number };

const KEY = "dfsp:pubkeys";

function loadAll(): ContactKey[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); }
  catch { return []; }
}

export function saveKey(address: string, pem: string) {
  const a = address.trim().toLowerCase();
  const rec: ContactKey = { address: a, pem, addedAt: Date.now() };
  const all = loadAll().filter(x => x.address !== a);
  all.push(rec);
  localStorage.setItem(KEY, JSON.stringify(all));
}

export function findKey(address: string): string | null {
  const a = address.trim().toLowerCase();
  const rec = loadAll().find(x => x.address === a);
  return rec?.pem ?? null;
}

