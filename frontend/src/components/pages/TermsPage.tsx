import Layout from '../Layout';
import { Link } from 'react-router-dom';

export default function TermsPage() {
  return (
    <Layout>
      <div className="max-w-5xl mx-auto">
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-8 sm:p-10 md:p-12">
          <div className="prose max-w-none">
            <h1 className="mb-4 text-3xl font-semibold tracking-tight">DFSP — Terms of Use</h1>
            <h2>1. Who we are</h2>
            <p>DFSP (“we”, “us”, “our”) provides a decentralized file storage and proof platform. We do not custody user private keys and cannot recover access to user wallets.</p>
            <p><strong>Contacts</strong><br/>Support & legal notices: <a href="mailto:mail@dfsp.app">mail@dfsp.app</a><br/>Registered entity: <strong>TBD</strong> (to be updated once available).</p>
            <h2>2. Acceptance of the Terms</h2>
            <p>By accessing or using DFSP, you agree to these Terms of Use. If you do not agree, do not use the Service.</p>
            <h2>3. Service Description</h2>
            <p>DFSP allows users to anchor and verify file metadata on a public blockchain and store content via IPFS or similar networks. Some functionality may rely on third‑party networks and providers.</p>
            <h2>4. Eligibility</h2>
            <p>You must be at least <strong>13 years old</strong> to use the Service. The Service is available globally except where prohibited by applicable law.</p>
            <h2>5. Non‑custodial & Web3 Risks</h2>
            <ul>
              <li>You are solely responsible for your wallet, private keys, and recovery phrases. We cannot recover your access.</li>
              <li>Network fees (gas), delays, re‑orgs, or failures may occur. Smart contracts may contain bugs. Use at your own risk.</li>
              <li>Interactions with external wallets (e.g., WalletConnect/MetaMask) are at your discretion.</li>
            </ul>
            <h2>6. Fees</h2>
            <p>The Service is currently free; we may introduce fees later with prior notice in these Terms and/or in‑app.</p>
            <h2>7. Content and Storage</h2>
            <ul>
              <li>You control what you upload or anchor. You must not upload or use the Service for illegal content or content infringing third‑party rights.</li>
              <li>IPFS and blockchains may be immutable; removal may be technically impossible. We may restrict access through our interface when we receive valid notices.</li>
              <li>You retain ownership of your content.</li>
            </ul>
            <h2>8. Prohibited Use</h2>
            <p>You agree not to use the Service for: (a) unlawful purposes; (b) malware, fraud, or spam; (c) violating intellectual property, privacy, or other rights; (d) attempting to interfere with Service integrity or security.</p>
            <h2>9. Telegram Bot</h2>
            <p>Linking your wallet to a Telegram chat uses a one‑time token with short TTL. We never store private keys. Notifications are optional and may be rate‑limited or paused.</p>
            <h2>10. Third‑Party Services</h2>
            <p>The Service may rely on third‑party infrastructure (e.g., hosting, IPFS, blockchain nodes, analytics limited to infrastructure metrics). Their terms and policies apply separately.</p>
            <h2>11. “As Is” Disclaimer</h2>
            <p><strong>THE SERVICE IS PROVIDED “AS IS” AND “AS AVAILABLE” WITHOUT WARRANTIES OF ANY KIND.</strong> We disclaim all implied warranties to the fullest extent permitted by law.</p>
            <h2>12. Limitation of Liability</h2>
            <p>To the maximum extent permitted by law, DFSP and its affiliates will not be liable for indirect, incidental, special, consequential, exemplary, or punitive damages, nor for any loss of data, profits, or goodwill, or for blockchain/network failures, even if advised of the possibility of such damages.</p>
            <h2>13. Indemnification</h2>
            <p>You agree to defend, indemnify, and hold harmless DFSP from claims arising out of your use of the Service or violation of these Terms.</p>
            <h2>14. Changes to the Service and Terms</h2>
            <p>We may modify or discontinue features at any time. We may update these Terms by posting an updated version. Continued use after the “Effective date” constitutes acceptance. Material changes may be announced in‑app and/or by email (if provided).</p>
            <h2>15. Dispute Resolution, Governing Law, Arbitration</h2>
            <ul>
              <li>Governing law: <strong>TBD</strong> (default recommendation: England and Wales).</li>
              <li>Binding arbitration and <strong>class action waiver</strong> apply to the extent permitted by law. Details will be finalized when the legal entity is determined.</li>
            </ul>
            <h2>16. Contact</h2>
            <p>Questions: <a href="mailto:mail@dfsp.app">mail@dfsp.app</a></p>
          </div>
          <div className="mt-10 flex justify-between items-center">
            <a href="/register" className="text-sm text-blue-600 hover:text-blue-700">Create an account</a>
            <a href="/login" className="text-sm text-blue-600 hover:text-blue-700">Back to login</a>
          </div>
        </div>
      </div>
    </Layout>
  );
}
