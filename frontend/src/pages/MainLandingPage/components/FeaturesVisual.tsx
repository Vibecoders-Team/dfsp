import { Lock, Database, Users, RotateCcw, Zap, FileCheck } from "lucide-react";

const features = [
	{
		icon: Lock,
		title: "Client-Side Encryption",
		description:
			"AES-GCM encryption before upload. Keys delivered to recipients via RSA-OAEP. Your files are always protected end-to-end.",
		color: "cyan",
		gradient: "from-cyan-500/10 to-cyan-500/5",
	},
	{
		icon: Database,
		title: "Content-Addressed Storage",
		description:
			"Files stored on IPFS with integrity verification via CID and on-chain checksums. Immutable and verifiable.",
		color: "fuchsia",
		gradient: "from-fuchsia-500/10 to-fuchsia-500/5",
	},
	{
		icon: Users,
		title: "Flexible Access Control",
		description:
			"Share with individuals, create recipient lists, or generate ephemeral public links with TTL and download limits.",
		color: "green",
		gradient: "from-green-500/10 to-green-500/5",
	},
	{
		icon: RotateCcw,
		title: "Revocation & Versioning",
		description:
			"Instantly revoke access to any file. Publish new versions with preserved history and audit trail.",
		color: "orange",
		gradient: "from-orange-500/10 to-orange-500/5",
	},
	{
		icon: Zap,
		title: "Gasless Transactions",
		description:
			"ERC-2771 minimal forwarder + relayer system. No wallets to manage, no transaction fees for users.",
		color: "yellow",
		gradient: "from-yellow-500/10 to-yellow-500/5",
	},
	{
		icon: FileCheck,
		title: "Full Auditability",
		description:
			"Hourly Merkle anchoring of off-chain event logs to blockchain. Complete transparency without chain bloat.",
		color: "blue",
		gradient: "from-blue-500/10 to-blue-500/5",
	},
];

export function FeaturesVisual() {
	return (
		<div className="relative border-b border-zinc-800 bg-zinc-950">
			<div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900 via-zinc-950 to-zinc-950" />

			<div className="relative mx-auto max-w-7xl px-6 py-24 lg:px-8">
				<div className="mx-auto max-w-2xl text-center mb-16">
					<div className="mb-4 inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/50 px-4 py-1.5 text-sm text-zinc-400">
						<div className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
						Core Capabilities
					</div>
					<h2 className="mb-4 text-zinc-100">Powerful Features</h2>
					<p className="text-lg text-zinc-400">
						Enterprise-grade security and decentralization without compromising on
						user experience
					</p>
				</div>

				<div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
					{features.map((feature, index) => (
						<div
							key={index}
							className="group relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/50 p-8 backdrop-blur-sm transition-all hover:border-zinc-700"
						>
							<div
								className={`absolute inset-0 bg-gradient-to-br ${feature.gradient} opacity-0 transition-opacity group-hover:opacity-100`}
							/>

							<div className="relative mb-5">
								<div
									className={`inline-flex h-14 w-14 items-center justify-center rounded-xl bg-${feature.color}-500/10 ring-1 ring-${feature.color}-500/20 transition-all group-hover:scale-110 group-hover:ring-2`}
								>
									<feature.icon
										className={`h-7 w-7 text-${feature.color}-400`}
									/>
								</div>
							</div>

							<h3 className="relative mb-3 text-xl text-zinc-100">
								{feature.title}
							</h3>
							<p className="relative text-zinc-400">
								{feature.description}
							</p>

							<div
								className={`absolute bottom-0 right-0 h-32 w-32 bg-gradient-to-tl ${feature.gradient} opacity-0 blur-2xl transition-opacity group-hover:opacity-100`}
							/>
						</div>
					))}
				</div>

				<div className="mt-20 rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-10 backdrop-blur-sm">
					<div className="text-center mb-8">
						<h3 className="mb-3 text-2xl text-zinc-100">
							Built With Industry Standards
						</h3>
						<p className="text-zinc-400">
							Proven, audited, and battle-tested technologies
						</p>
					</div>
					<div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
						{[
							{ name: "IPFS", desc: "Storage" },
							{ name: "EVM", desc: "Blockchain" },
							{ name: "AES-GCM", desc: "Encryption" },
							{ name: "RSA-OAEP", desc: "Key Exchange" },
							{ name: "ERC-2771", desc: "Meta Txns" },
							{ name: "Merkle", desc: "Anchoring" },
						].map((tech) => (
							<div
								key={tech.name}
								className="group relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 text-center transition-all hover:border-zinc-700 hover:bg-zinc-900"
							>
								<div className="text-zinc-200 mb-1">{tech.name}</div>
								<div className="text-xs text-zinc-500">{tech.desc}</div>
							</div>
						))}
					</div>
				</div>
			</div>
		</div>
	);
}
