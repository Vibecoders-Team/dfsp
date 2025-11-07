export function getOrCreateFileKey(fileId: string): Uint8Array {
  const k = localStorage.getItem(`dfsp:filekey:${fileId}`);
  if (k) return new Uint8Array(JSON.parse(k));
  const key = crypto.getRandomValues(new Uint8Array(32));
  localStorage.setItem(`dfsp:filekey:${fileId}`, JSON.stringify(Array.from(key)));
  return key;
}

