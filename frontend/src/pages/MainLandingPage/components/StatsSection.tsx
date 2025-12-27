import { Shield, Zap, Users, FileCheck } from "lucide-react";

const stats = [
	{
		icon: Shield,
		value: "256-bit",
		label: "AES Encryption",
		color: "cyan",
	},
	{
		icon: Zap,
		value: "$0",
		label: "Transaction Fees",
		color: "fuchsia",
	},
	{
		icon: Users,
		value: "∞",
		label: "Recipients",
		color: "green",
	},
	{
		icon: FileCheck,
		value: "100%",
		label: "On-Chain Verified",
		color: "orange",
	},
];

export function StatsSection() {
	return (
		<div className="relative border-b border-zinc-800 bg-zinc-950">
			<div className="absolute inset-0 bg-gradient-to-b from-zinc-950 via-zinc-900/50 to-zinc-950" />

			<div className="relative mx-auto max-w-7xl px-6 py-16 lg:px-8">
				<div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
					{stats.map((stat, index) => (
						<div
							key={index}
							className="group relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/30 p-8 text-center backdrop-blur-sm transition-all hover:border-zinc-700"
						>
							<div
								className={`absolute inset-0 bg-gradient-to-br from-${stat.color}-500/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100`}
							/>

							<div className="relative">
								<div className="mb-4 flex justify-center">
									<div
										className={`flex h-12 w-12 items-center justify-center rounded-full bg-${stat.color}-500/10 ring-1 ring-${stat.color}-500/20`}
									>
										<stat.icon
											className={`h-6 w-6 text-${stat.color}-400`}
										/>
									</div>
								</div>
								<div
									className={`mb-2 bg-gradient-to-br from-${stat.color}-300 to-${stat.color}-500 bg-clip-text text-transparent`}
								>
									{stat.value}
								</div>
								<div className="text-sm text-zinc-400">
									{stat.label}
								</div>
							</div>
						</div>
					))}
				</div>
			</div>
		</div>
	);
}
