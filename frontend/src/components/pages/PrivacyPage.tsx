import Layout from '../Layout';

export default function PrivacyPage() {
  return (
    <Layout publicDoc>
      <div className="max-w-5xl mx-auto">
        <div className="bg-card border border-border rounded-xl shadow-sm p-8 sm:p-10 md:p-12">
          <div className="prose dark:prose-invert max-w-none">
            <h1 className="mb-4 text-3xl font-semibold tracking-tight">DFSP — Privacy Policy</h1>
            <h2>1. Summary</h2>
            <ul>
              <li>We minimize data. We do <strong>not</strong> store private keys or file encryption keys.</li>
              <li>We process: wallet address, optional display name, RSA public key, Telegram <code>chat_id</code>, file metadata (IDs, checksums, sizes, MIME, CIDs), and operational telemetry.</li>
              <li>No marketing tracking. Infrastructure metrics only (Prometheus/Grafana, local).</li>
              <li>Users can request access/correction/deletion via <a href="mailto:mail@dfsp.app">mail@dfsp.app</a>.</li>
            </ul>
            <h2>2. Data Controller</h2>
            <p>DFSP (entity <strong>TBD</strong>). Contact: <a href="mailto:mail@dfsp.app">mail@dfsp.app</a>.</p>
            <h2>3. What we collect</h2>
            <ul>
              <li><strong>Account</strong>: wallet address, optional display name, RSA public key.</li>
              <li><strong>Telegram link</strong>: <code>chat_id</code> and wallet address link, one‑time tokens for linking (short TTL).</li>
              <li><strong>Content metadata</strong>: fileId (bytes32/hex), name, size, MIME, checksum (keccak), CID (IPFS), owner address.</li>
              <li><strong>Action intents</strong>: short‑lived identifiers for handoff flows (state with TTL).</li>
              <li><strong>Operational data</strong>: basic service logs and metrics; we do <strong>not</strong> store IP addresses or user‑agents beyond transient processing.</li>
              <li><strong>No cookies tracking</strong> beyond what is strictly necessary for authentication tokens.</li>
            </ul>
            <h2>4. Purpose & Legal Bases</h2>
            <ul>
              <li><strong>Provide the Service</strong> (contract): account lifecycle, uploads, verification, sharing, revoke.</li>
              <li><strong>Security & abuse prevention</strong> (legitimate interests): rate‑limits, anti‑spam for bot, integrity checks.</li>
              <li><strong>Service analytics</strong> (legitimate interests): aggregated, minimal metrics to maintain reliability.</li>
              <li><strong>Compliance</strong> (legal obligation): honoring rights requests, lawful notices.</li>
            </ul>
            <h2>5. Sharing with Third Parties</h2>
            <ul>
              <li><strong>Infrastructure</strong>: hosting (e.g., DigitalOcean), storage, databases, message queues, monitoring.</li>
              <li><strong>Networks</strong>: blockchain/RPC nodes (own or third‑party), IPFS gateways/pinning.</li>
              <li>We do not sell or share personal data for marketing.</li>
            </ul>
            <h2>6. International Transfers</h2>
            <p>We may process data globally where our infrastructure or providers operate. Where required by law, we will use appropriate safeguards (e.g., Standard Contractual Clauses) — details to be updated when the entity/jurisdiction is finalized.</p>
            <h2>7. Retention</h2>
            <ul>
              <li><strong>Account data</strong>: as long as the account is active.</li>
              <li><strong>Telegram link</strong>: until user unlinks.</li>
              <li><strong>Action intents</strong>: TTL (≈10–15 minutes), then deleted/expired.</li>
              <li><strong>Operational logs/metrics</strong>: minimal and ephemeral; no IP/user‑agent retention beyond transient processing.</li>
              <li><strong>Immutable records</strong>: blockchain/IPFS content may be technically non‑removable.</li>
            </ul>
            <h2>8. Your Rights</h2>
            <p>Subject to applicable law, you can request access, correction, deletion, restriction, objection, or portability by contacting <a href="mailto:mail@dfsp.app">mail@dfsp.app</a>. We typically respond within <strong>1 business day</strong>.</p>
            <h2>9. Children</h2>
            <p>The Service is not directed to children under <strong>13</strong>. Do not use the Service if you are under 13.</p>
            <h2>10. Security</h2>
            <p>TLS in transit; least‑privilege access; no storage of private keys or file encryption keys. We will notify users of a data incident without undue delay where required by law.</p>
            <h2>11. Changes</h2>
            <p>We may update this Policy from time to time. Material changes will be notified in‑app and/or by email (if available). The English version prevails.</p>
            <h2>12. Contact</h2>
            <p><a href="mailto:mail@dfsp.app">mail@dfsp.app</a></p>
          </div>
        </div>
      </div>
    </Layout>
  );
}
