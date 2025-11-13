import { describe, it, expect } from 'vitest';
import { encryptFile, decryptStream } from '../cryptoClient';

function toFile(data: string, name = 'test.txt', type='text/plain'): File {
  return new File([data], name, { type });
}

function randomChunks(u8: Uint8Array): Uint8Array[] {
  const out: Uint8Array[] = [];
  let i = 0;
  while (i < u8.length) {
    const left = u8.length - i;
    const sz = Math.max(1, Math.min(left, Math.floor(Math.random()*8192))); // up to 8KB random
    out.push(u8.slice(i, i+sz));
    i += sz;
  }
  return out;
}

describe('stream roundtrip decrypt', () => {
  it('encrypts and decrypts via Response stream', async () => {
    const text = 'Hello DFSP streaming! ' + 'x'.repeat(200_000);
    const file = toFile(text);
    const key = crypto.getRandomValues(new Uint8Array(32));
    const enc = await encryptFile(file, key, 64*1024);
    const buf = new Uint8Array(await enc.blob.arrayBuffer());
    const chunks = randomChunks(buf);

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        (async () => {
          for (const c of chunks) {
            controller.enqueue(c);
            await new Promise(r => setTimeout(r, 0));
          }
          controller.close();
        })();
      }
    });
    const resp = new Response(stream);
    const decBlob = await decryptStream(resp, key);
    const decText = await decBlob.text();
    expect(decText).toBe(text);
  });
});

