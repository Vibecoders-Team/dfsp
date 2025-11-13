// Frontend wrapper for crypto.worker
// Provides: hkdf, keccak, encryptFile(file, key), decryptStream(stream, key)

export type EncryptProgressCb = (encryptedBytes: number, total: number) => void;

let cryptoWorker: Worker | null = null;
const useDirect = (typeof Worker === 'undefined');
// helpers for direct mode
function u32be(n:number){ const b=new ArrayBuffer(4); new DataView(b).setUint32(0,n,false); return new Uint8Array(b); }
async function directHKDF(ikm:ArrayBuffer, salt?:ArrayBuffer, info?:ArrayBuffer, length=32){
  const material = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return crypto.subtle.deriveBits({ name:'HKDF', hash:'SHA-256', salt: salt || new Uint8Array(), info: info || new Uint8Array() }, material, length*8);
}
let d_encKey: CryptoKey | null = null; let d_chunkSize = 64*1024; let d_total = 0; let d_decKey: CryptoKey | null = null; let d_decIndex = 0;
async function importAes(raw:ArrayBuffer){ return crypto.subtle.importKey('raw', raw, { name:'AES-GCM' }, false, ['encrypt','decrypt']); }
async function directEncChunk(index:number, chunk:ArrayBuffer){ if(!d_encKey) throw new Error('encKey not set'); const iv=crypto.getRandomValues(new Uint8Array(12)); const ct=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:u32be(index)}, d_encKey, chunk); const out=new Uint8Array(12+4+new Uint8Array(ct).length); out.set(iv,0); out.set(u32be(new Uint8Array(ct).length),12); out.set(new Uint8Array(ct),16); return out.buffer; }
function makeHeader(chunkSize:number,total:number){ const MAGIC=new Uint8Array([0x44,0x46,0x53,0x50]); const out=new Uint8Array(4+1+4+8); out.set(MAGIC,0); out[4]=1; out.set(u32be(chunkSize),5); const dv=new DataView(out.buffer,9); const hi=Math.floor(total/2**32); const lo=total>>>0; dv.setUint32(0,hi,false); dv.setUint32(4,lo,false); return out.buffer; }
function parseHeader(header:ArrayBuffer){ const u8=new Uint8Array(header); if(u8[0]!==0x44||u8[1]!==0x46||u8[2]!==0x53||u8[3]!==0x50) throw new Error('bad_magic'); const cs=new DataView(header,5,4).getUint32(0,false); const dv=new DataView(header,9,8); const total=dv.getUint32(0,false)*2**32 + dv.getUint32(4,false); return {chunkSize:cs,totalSize:total}; }
async function directDecChunk(chunk:ArrayBuffer){ if(!d_decKey) throw new Error('decKey not set'); const u8=new Uint8Array(chunk); const iv=u8.slice(0,12); const ctLen=new DataView(u8.buffer,u8.byteOffset+12,4).getUint32(0,false); const ct=u8.slice(16,16+ctLen); const ad=u32be(d_decIndex); const pt = await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:ad}, d_decKey, ct); d_decIndex += 1; return pt; }

function getWorker(): Worker {
  if (useDirect) throw new Error('no_worker');
  if (!cryptoWorker) {
    cryptoWorker = new Worker(new URL('../workers/crypto.worker.ts', import.meta.url), { type: 'module' });
  }
  return cryptoWorker;
}

function postMessage<T extends CryptoReq, R>(msg: T): Promise<R> {
  if (useDirect) {
    const m = msg as CryptoReq;
    return (async()=>{
      switch(m.cmd){
        case 'hkdf': {
          const bytes = await directHKDF(m.ikm, m.salt, m.info, (m as any).length);
          return { ok:true, bytes } as unknown as R;
        }
        case 'enc_init': {
          d_encKey = await importAes(m.key); d_chunkSize=(m as any).chunkSize; d_total=(m as any).totalSize; return { ok:true } as unknown as R;
        }
        case 'enc_chunk': {
          const out = await directEncChunk((m as any).index, (m as any).chunk); return { ok:true, out } as unknown as R;
        }
        case 'enc_final': { const header = makeHeader(d_chunkSize, d_total); return { ok:true, header } as unknown as R; }
        case 'dec_init': { d_decKey = await importAes(m.key); d_decIndex = 0; return { ok:true } as unknown as R; }
        case 'dec_header': { const meta = parseHeader((m as any).header); return { ok:true, ...meta } as unknown as R; }
        case 'dec_chunk': { const out = await directDecChunk((m as any).chunk); return { ok:true, out } as unknown as R; }
        case 'keccak': { const mod = await import('ethers'); const hex = mod.keccak256(new Uint8Array((m as any).data)); return { ok:true, hex } as unknown as R; }
        default: throw new Error('unknown_cmd');
      }
    })();
  }
  const w = getWorker();
  return new Promise((resolve, reject) => {
    const handler = (ev: MessageEvent) => {
      const data = ev.data;
      if (data && (data.ok || data.error)) {
        w.removeEventListener('message', handler);
        if (data.ok) resolve(data as R); else reject(new Error(data.error || 'worker_error'));
      }
    };
    w.addEventListener('message', handler);
    w.postMessage(msg);
  });
}

export async function hkdf(ikm: Uint8Array, length=32, salt?: Uint8Array, info?: Uint8Array): Promise<Uint8Array> {
  const { bytes } = await postMessage<{cmd:'hkdf'; ikm:ArrayBuffer; length:number; salt?:ArrayBuffer; info?:ArrayBuffer}, { ok:true; bytes:ArrayBuffer }>({
    cmd:'hkdf', ikm: ikm.buffer, length, salt: salt?.buffer, info: info?.buffer
  });
  return new Uint8Array(bytes);
}

export async function keccak(data: Uint8Array): Promise<string> {
  const { hex } = await postMessage<{cmd:'keccak'; data:ArrayBuffer}, { ok:true; hex:string }>({ cmd:'keccak', data: data.buffer });
  return hex;
}

export interface EncryptResult { blob: Blob; header: Uint8Array }

export async function encryptFile(file: File, rawKey: Uint8Array, chunkSize=64*1024, onProgress?: EncryptProgressCb): Promise<EncryptResult> {
  await postMessage({ cmd:'enc_init', key: rawKey.buffer, chunkSize, totalSize: file.size });
  const reader = file.stream().getReader();
  let index = 0; let encryptedBytes = 0; const encryptedParts: BlobPart[] = [];
  while(true){
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      const { out } = await postMessage<{cmd:'enc_chunk'; index:number; chunk:ArrayBuffer}, { ok:true; out:ArrayBuffer }>({ cmd:'enc_chunk', index, chunk: value.buffer });
      encryptedParts.push(out);
      encryptedBytes += (value.byteLength);
      index += 1;
      onProgress?.(encryptedBytes, file.size);
    }
  }
  const { header } = await postMessage<{cmd:'enc_final'}, { ok:true; header:ArrayBuffer }>({ cmd:'enc_final' });
  const blob = new Blob([header, ...encryptedParts], { type: 'application/octet-stream' });
  return { blob, header: new Uint8Array(header) };
}

function isDfspHeader(buf: Uint8Array): boolean { return buf.length>=4 && buf[0]===0x44 && buf[1]===0x46 && buf[2]===0x53 && buf[3]===0x50; }

export async function decryptStream(resp: Response, rawKey: Uint8Array, onProgress?: (decrypted:number, total:number)=>void): Promise<Blob> {
  const reader = resp.body?.getReader(); if(!reader) throw new Error('no_body');
  // 1) Read exactly 17 bytes header
  const header = new Uint8Array(17);
  let filled = 0;
  let carry: Uint8Array | null = null;
  while (filled < 17) {
    const { done, value } = await reader.read();
    if (done) throw new Error('incomplete_header');
    if (!value || value.length === 0) continue;
    const need = 17 - filled;
    const take = Math.min(need, value.length);
    header.set(value.slice(0, take), filled);
    filled += take;
    if (value.length > take) {
      carry = value.slice(take);
      break;
    }
  }
  // init decrypt
  await postMessage({ cmd:'dec_init', key: rawKey.buffer });
  const { totalSize } = await postMessage<{cmd:'dec_header'; header:ArrayBuffer}, { ok:true; chunkSize:number; totalSize:number }>({ cmd:'dec_header', header: header.buffer });

  // 2) Frame parsing loop: each frame = 12-byte IV + 4-byte big-endian ctLen + ct
  let pending = carry ? new Uint8Array(carry) : new Uint8Array(0);
  const outParts: BlobPart[] = [];
  let decrypted = 0;

  // helper to process pending buffer extracting full frames
  const processPending = async () => {
    while (pending.length >= 16) {
      const ivLen = 12;
      const lenView = new DataView(pending.buffer, pending.byteOffset + ivLen, 4);
      const ctLen = lenView.getUint32(0, false);
      const frameLen = 16 + ctLen;
      if (pending.length < frameLen) break;
      const frame = pending.slice(0, frameLen);
      const { out } = await postMessage<{cmd:'dec_chunk'; chunk:ArrayBuffer}, { ok:true; out:ArrayBuffer }>({ cmd:'dec_chunk', chunk: frame.buffer.slice(frame.byteOffset, frame.byteOffset + frame.length) });
      outParts.push(out);
      decrypted += new Uint8Array(out).length;
      onProgress?.(decrypted, totalSize);
      pending = pending.slice(frameLen);
    }
  };

  // process initial carry
  await processPending();

  // read network stream
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (!value || value.length === 0) continue;
    // append to pending
    if (pending.length === 0) pending = value; else {
      const merged = new Uint8Array(pending.length + value.length);
      merged.set(pending, 0); merged.set(value, pending.length);
      pending = merged;
    }
    await processPending();
  }

  if (pending.length !== 0) {
    throw new Error('truncated_encrypted_stream');
  }
  const finalBlob = new Blob(outParts, { type:'application/octet-stream' });
  // sanity: if plaintext starts with DFSP magic -> we accidentally returned encrypted container
  const headCheck = new Uint8Array(await finalBlob.slice(0,4).arrayBuffer());
  if (isDfspHeader(headCheck)) {
    throw new Error('still_encrypted_container');
  }
  return finalBlob;
}
