// Quick self-check for WalletConnect relay reachability from this environment.
// Run: node scripts/wc-relay-check.mjs

import net from 'node:net';
import tls from 'node:tls';

function tcpConnect(host, port, timeoutMs = 5000) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const t = setTimeout(() => {
      socket.destroy();
      resolve({ ok: false, kind: 'timeout' });
    }, timeoutMs);
    socket.once('connect', () => {
      clearTimeout(t);
      socket.end();
      resolve({ ok: true, kind: 'tcp' });
    });
    socket.once('error', (e) => {
      clearTimeout(t);
      resolve({ ok: false, kind: 'error', err: String(e?.message || e) });
    });
  });
}

async function tlsHello(host, port = 443, timeoutMs = 8000) {
  return new Promise((resolve) => {
    const socket = tls.connect({ host, port, servername: host, ALPNProtocols: ['h2', 'http/1.1'] });
    const t = setTimeout(() => {
      socket.destroy();
      resolve({ ok: false, kind: 'timeout' });
    }, timeoutMs);
    socket.once('secureConnect', () => {
      clearTimeout(t);
      const proto = socket.alpnProtocol;
      const cipher = socket.getCipher();
      socket.end();
      resolve({ ok: true, kind: 'tls', alpn: proto, cipher: cipher?.name });
    });
    socket.once('error', (e) => {
      clearTimeout(t);
      resolve({ ok: false, kind: 'error', err: String(e?.message || e) });
    });
  });
}

async function main() {
  const targets = [
    { name: 'relay.walletconnect.com', host: 'relay.walletconnect.com', port: 443 },
    { name: 'api.web3modal.com', host: 'api.web3modal.com', port: 443 },
    { name: 'explorer.walletconnect.com', host: 'explorer.walletconnect.com', port: 443 },
  ];

  for (const t of targets) {
    const tcp = await tcpConnect(t.host, t.port);
    const tlsr = await tlsHello(t.host, t.port);
    // eslint-disable-next-line no-console
    console.log(
      `${t.name}: tcp=${tcp.ok ? 'OK' : 'FAIL'} (${tcp.kind}${tcp.err ? `: ${tcp.err}` : ''}), ` +
      `tls=${tlsr.ok ? 'OK' : 'FAIL'} (${tlsr.kind}${tlsr.err ? `: ${tlsr.err}` : ''})` +
      `${tlsr.alpn ? ` alpn=${tlsr.alpn}` : ''}${tlsr.cipher ? ` cipher=${tlsr.cipher}` : ''}`
    );
  }
}

try {
  await main();
} catch (e) {
  // eslint-disable-next-line no-console
  console.error('wc-relay-check failed:', e);
  process.exitCode = 1;
} finally {
  // Some environments keep sockets alive; force a clean exit after a short grace period.
  setTimeout(() => process.exit(process.exitCode ?? 0), 50);
}
