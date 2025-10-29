// scripts/export-deployment.ts
import fs from "fs";
import path from "path";
import {artifacts} from "hardhat";

async function main() {
    const configPath = process.env.CHAIN_CONFIG_PATH || "chain-config.json";
    const outPath = process.env.DEPLOY_OUT || "deployments/deployment.localhost.json";
    const networkName = process.env.NETWORK || "localhost";

    const raw = fs.readFileSync(configPath, "utf8");
    const cfg = JSON.parse(raw);

    const chainId = Number(cfg.chainId ?? 31337);
    const verifyingContracts: Record<string, string> = cfg.verifyingContracts || {};

    const contracts: Record<string, any> = {};
    for (const [name, address] of Object.entries(verifyingContracts)) {
        try {
            const art = await artifacts.readArtifact(name);
            contracts[name] = {address, abi: art.abi};
        } catch (e) {
            throw new Error(`Artifact for ${name} not found. Make sure contract name matches artifact name.`);
        }
    }

    const out = {network: networkName, chainId, contracts};
    fs.mkdirSync(path.dirname(outPath), {recursive: true});
    fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
    console.log(`✓ Wrote ${outPath}`);
}

main().catch((e) => {
    console.error(e);
    process.exit(1);
});
