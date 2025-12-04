# Browser Support & Polyfills

Baseline tested browsers:
- Chrome / Edge 92+
- Firefox 90+
- Safari 15+ (including iOS 15+)

Polyfills loaded by the frontend (`src/polyfills.ts`):
- `crypto.subtle` fallback to `msCrypto` / `webkitSubtle` when available.
- `TextEncoder` / `TextDecoder` minimal UTF-8 polyfills when missing.

For older browsers, ensure IndexedDB and WebCrypto are enabled; if either is unavailable the app may not function. Clear site data and update the browser when encountering storage or crypto initialization errors.
