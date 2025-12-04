// Minimal polyfills for older browsers (crypto.subtle, TextEncoder/Decoder)

(function ensureCrypto() {
  const g = globalThis as unknown as { crypto?: Crypto & { msCrypto?: Crypto; webkitSubtle?: SubtleCrypto } };
  if (!g.crypto && (g as unknown as { msCrypto?: Crypto }).msCrypto) {
    g.crypto = (g as unknown as { msCrypto: Crypto }).msCrypto;
  }
  if (g.crypto && !g.crypto.subtle && (g.crypto as { webkitSubtle?: SubtleCrypto }).webkitSubtle) {
    (g.crypto as { subtle: SubtleCrypto }).subtle = (g.crypto as { webkitSubtle: SubtleCrypto }).webkitSubtle;
  }
})();

(function ensureTextEncoderDecoder() {
  if (typeof globalThis.TextEncoder === 'undefined') {
    class SimpleTextEncoder {
      encode(input = ''): Uint8Array {
        const str = unescape(encodeURIComponent(input));
        const arr = new Uint8Array(str.length);
        for (let i = 0; i < str.length; i++) arr[i] = str.charCodeAt(i);
        return arr;
      }
    }
    (globalThis as { TextEncoder?: typeof TextEncoder }).TextEncoder = SimpleTextEncoder as unknown as typeof TextEncoder;
  }
  if (typeof globalThis.TextDecoder === 'undefined') {
    class SimpleTextDecoder {
      decode(input?: BufferSource): string {
        if (!input) return '';
        const u8 = input instanceof ArrayBuffer ? new Uint8Array(input) : new Uint8Array(input as unknown as ArrayBufferLike);
        let str = '';
        for (let i = 0; i < u8.length; i++) str += String.fromCharCode(u8[i]);
        return decodeURIComponent(escape(str));
      }
    }
    (globalThis as { TextDecoder?: typeof TextDecoder }).TextDecoder = SimpleTextDecoder as unknown as typeof TextDecoder;
  }
})();
