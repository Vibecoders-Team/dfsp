import { describe, it, expect } from 'vitest';
import { hkdf, encryptFile } from '../cryptoClient';

function u8(n:number){ const a=new Uint8Array(n); for(let i=0;i<n;i++) a[i]=i&0xff; return a; }

class FakeFile implements File {
  readonly lastModified: number; readonly name: string; readonly size: number; readonly type: string; webkitRelativePath: string = '';
  private readonly buf: Uint8Array;
  constructor(buf: Uint8Array, name='test.bin', type='application/octet-stream'){
    this.buf = buf; this.name=name; this.type=type; this.size=buf.length; this.lastModified=Date.now();
  }
  arrayBuffer(): Promise<ArrayBuffer> { return Promise.resolve(this.buf.buffer); }
  slice(start?: number, end?: number, contentType?: string | undefined): Blob { return new Blob([this.buf.slice(start,end)], { type: contentType }); }
  stream(): ReadableStream<Uint8Array> { return new ReadableStream({ start: (ctl) => { ctl.enqueue(this.buf); ctl.close(); } }); }
  text(): Promise<string> { return Promise.resolve(''); }
  bytes(): Promise<Uint8Array> { return Promise.resolve(new Uint8Array(this.buf)); }
}

describe('HKDF + AES encrypt', () => {
  it('hkdf derives 32 bytes', async () => {
    const out = await hkdf(u8(16), 32, u8(8), u8(4));
    expect(out.length).toBe(32);
  });
  it('encryptFile produces non-empty blob and header', async () => {
    const file = new FakeFile(u8(1024));
    const key = u8(32);
    const res = await encryptFile(file as unknown as File, key);
    expect(res.header.length).toBe(17);
    const encSize = await res.blob.arrayBuffer().then(b=>b.byteLength);
    expect(encSize).toBeGreaterThan(17);
  });
});
