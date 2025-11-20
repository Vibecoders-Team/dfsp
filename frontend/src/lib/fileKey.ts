const LS_PREFIX = 'dfsp:filekey:'

export function getFileKey(fileId: string): Uint8Array | null {
  const k = localStorage.getItem(`${LS_PREFIX}${fileId}`);
  if (!k) return null;
  try { return new Uint8Array(JSON.parse(k)); } catch { return null; }
}

export function setFileKey(fileId: string, key: Uint8Array): void {
  localStorage.setItem(`${LS_PREFIX}${fileId}`, JSON.stringify(Array.from(key)));
}

export function removeFileKey(fileId: string): void {
  try { localStorage.removeItem(`${LS_PREFIX}${fileId}`); } catch { /* ignore */ }
}

export function renameFileKey(oldId: string, newId: string): void {
  if (oldId === newId) return;
  const val = localStorage.getItem(`${LS_PREFIX}${oldId}`);
  if (!val) return;
  localStorage.setItem(`${LS_PREFIX}${newId}`, val);
  try { localStorage.removeItem(`${LS_PREFIX}${oldId}`); } catch { /* ignore */ }
}

export function getOrCreateFileKey(fileId: string): Uint8Array {
  const exist = getFileKey(fileId);
  if (exist) return exist;
  const key = crypto.getRandomValues(new Uint8Array(32));
  setFileKey(fileId, key);
  return key;
}
