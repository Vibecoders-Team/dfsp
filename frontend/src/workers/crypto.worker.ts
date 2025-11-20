// Crypto worker: HKDF, AES-GCM chunked, keccak256
// Message protocol:
// { cmd: 'hkdf', ikm:ArrayBuffer, salt?:ArrayBuffer, info?:ArrayBuffer, length:number } => { ok:true, bytes:ArrayBuffer }
// { cmd: 'keccak', data:ArrayBuffer } => { ok:true, hex:string }
// { cmd: 'enc_init', key:ArrayBuffer, chunkSize:number, totalSize:number } => { ok:true }
// { cmd: 'enc_chunk', index:number, chunk:ArrayBuffer } => { ok:true, out:ArrayBuffer } // out = IV(12) + u32be(ctLen) + ct
// { cmd: 'enc_final' } => { ok:true, header:ArrayBuffer } // header = 'DFSP'(4)+ver(1)+u32be(chunkSize)+u64be(totalSize)
// { cmd: 'dec_init', key:ArrayBuffer } => { ok:true }
// { cmd: 'dec_header', header:ArrayBuffer } => { ok:true, chunkSize:number, totalSize:number }
// { cmd: 'dec_chunk', chunk:ArrayBuffer } => { ok:true, out:ArrayBuffer } // input chunk = IV(12)+u32be(ctLen)+ct

export type CryptoReq =
  | { cmd:'hkdf'; ikm:ArrayBuffer; salt?:ArrayBuffer; info?:ArrayBuffer; length:number }
  | { cmd:'keccak'; data:ArrayBuffer }
  | { cmd:'enc_init'; key:ArrayBuffer; chunkSize:number; totalSize:number }
  | { cmd:'enc_chunk'; index:number; chunk:ArrayBuffer }
  | { cmd:'enc_final' }
  | { cmd:'dec_init'; key:ArrayBuffer }
  | { cmd:'dec_header'; header:ArrayBuffer }
  | { cmd:'dec_chunk'; chunk:ArrayBuffer };

const MAGIC = new Uint8Array([0x44,0x46,0x53,0x50]); // 'DFSP'
const VERSION = 1;

let encKey: CryptoKey | null = null;
let decKey: CryptoKey | null = null;
let encChunkSize = 64*1024;
let encTotalSize = 0;
let decIndex = 0;

function u32be(n:number){ const b=new ArrayBuffer(4); new DataView(b).setUint32(0,n,false); return new Uint8Array(b); }
function u64be(n:number){ const b=new ArrayBuffer(8); const dv=new DataView(b); const hi=Math.floor(n/2**32); const lo=n>>>0; dv.setUint32(0,hi,false); dv.setUint32(4,lo,false); return new Uint8Array(b); }

async function doHKDF(ikm:ArrayBuffer, salt?:ArrayBuffer, info?:ArrayBuffer, length=32):Promise<ArrayBuffer> {
  const material = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  return crypto.subtle.deriveBits({ name:'HKDF', hash:'SHA-256', salt: salt || new Uint8Array(), info: info || new Uint8Array() }, material, length*8);
}

async function importAesKey(raw:ArrayBuffer):Promise<CryptoKey>{
  return crypto.subtle.importKey('raw', raw, { name:'AES-GCM' }, false, ['encrypt','decrypt']);
}

async function encChunk(index:number, chunk:ArrayBuffer):Promise<ArrayBuffer>{
  if(!encKey) throw new Error('encKey not set');
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name:'AES-GCM', iv, additionalData: u32be(index) }, encKey, chunk);
  const ctU8 = new Uint8Array(ct);
  const out = new Uint8Array(12 + 4 + ctU8.length);
  out.set(iv,0); out.set(u32be(ctU8.length),12); out.set(ctU8,16);
  return out.buffer;
}

async function decChunk(chunk:ArrayBuffer):Promise<ArrayBuffer>{
  if(!decKey) throw new Error('decKey not set');
  const u8 = new Uint8Array(chunk);
  const iv = u8.slice(0,12);
  const ctLen = new DataView(u8.buffer, u8.byteOffset+12, 4).getUint32(0, false);
  const ct = u8.slice(16, 16+ctLen);
  const idxBytes = u32be(decIndex);
  const pt = await crypto.subtle.decrypt({ name:'AES-GCM', iv, additionalData: idxBytes }, decKey, ct);
  decIndex += 1;
  return pt;
}

function makeHeader():ArrayBuffer{
  const out = new Uint8Array(4+1+4+8);
  out.set(MAGIC,0); out[4]=VERSION; out.set(u32be(encChunkSize),5); out.set(u64be(encTotalSize),9);
  return out.buffer;
}

function parseHeader(header:ArrayBuffer){
  const u8 = new Uint8Array(header);
  if (u8.length < 17) throw new Error('bad_header');
  if (u8[0]!==0x44||u8[1]!==0x46||u8[2]!==0x53||u8[3]!==0x50) throw new Error('bad_magic');
  const ver = u8[4]; if(ver!==VERSION) throw new Error('bad_version');
  const cs = new DataView(u8.buffer, u8.byteOffset+5, 4).getUint32(0,false);
  const hi = new DataView(u8.buffer, u8.byteOffset+9, 4).getUint32(0,false);
  const lo = new DataView(u8.buffer, u8.byteOffset+13, 4).getUint32(0,false);
  const total = hi * 2**32 + lo;
  return { chunkSize: cs, totalSize: total };
}

// keccak via ethers (dynamically import)
async function keccakHex(data:ArrayBuffer):Promise<string>{
  const mod = await import('ethers');
  const u8 = new Uint8Array(data);
  return mod.keccak256(u8);
}

const ctx = self as unknown as DedicatedWorkerGlobalScope;

self.addEventListener('message', async (ev: MessageEvent<CryptoReq>) => {
  const m = ev.data;
  try {
    switch(m.cmd){
      case 'hkdf': {
        const out = await doHKDF(m.ikm, m.salt, m.info, m.length);
        ctx.postMessage({ ok:true, bytes: out }, [out as ArrayBuffer]);
        break;
      }
      case 'keccak':{
        const hex = await keccakHex(m.data);
        ctx.postMessage({ ok:true, hex });
        break;
      }
      case 'enc_init':{
        encKey = await importAesKey(m.key); encChunkSize = m.chunkSize; encTotalSize = m.totalSize;
        ctx.postMessage({ ok:true });
        break;
      }
      case 'enc_chunk':{
        const out = await encChunk(m.index, m.chunk);
        ctx.postMessage({ ok:true, out }, [out as ArrayBuffer]);
        break;
      }
      case 'enc_final':{
        const header = makeHeader();
        ctx.postMessage({ ok:true, header }, [header as ArrayBuffer]);
        break;
      }
      case 'dec_init':{
        decKey = await importAesKey(m.key);
        decIndex = 0; // reset frame counter
        ctx.postMessage({ ok:true });
        break;
      }
      case 'dec_header':{
        const meta = parseHeader(m.header);
        ctx.postMessage({ ok:true, ...meta });
        break;
      }
      case 'dec_chunk':{
        const out = await decChunk(m.chunk);
        ctx.postMessage({ ok:true, out }, [out as ArrayBuffer]);
        break;
      }
      default:
        ctx.postMessage({ ok:false, error:'unknown_cmd' });
    }
  } catch(e: unknown){
    const msg = (e as Error)?.message || String(e);
    ctx.postMessage({ ok:false, error: msg });
  }
});
