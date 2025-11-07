// scripts/export-deployment.ts
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import hre from "hardhat";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function readArtifactSafe(name: string) {
  try {
    return await hre.artifacts.readArtifact(name);
  } catch {
    // Fallback на FQN под src/
    const fqn = `src/${name}.sol:${name}`;
    try {
      return await hre.artifacts.readArtifact(fqn);
    } catch {
      throw new Error(`Artifact for ${name} not found. Tried: '${name}', '${fqn}'.`);
    }
  }
}

async function main() {
  // По умолчанию ищем тот файл, который создаёт deploy-local.ts: ../deploy/chain-config.json
  const defaultCfg = path.resolve(__dirname, "../deploy/chain-config.json");
  const configPath = process.env.CHAIN_CONFIG_PATH || defaultCfg;

  // Куда писать итог (можно переопределить DEPLOY_OUT)
  const defaultOut = path.resolve("deployments/deployment.localhost.json");
  const outPath = process.env.DEPLOY_OUT || defaultOut;

  const networkName = process.env.NETWORK || "localhost";

  const raw = fs.readFileSync(configPath, "utf8");
  const cfg = JSON.parse(raw);

  const chainId = Number(cfg.chainId ?? 31337);
  const verifyingContracts: Record<string, string> = cfg.verifyingContracts || {};

  const contracts: Record<string, any> = {};
  for (const [name, address] of Object.entries(verifyingContracts)) {
    const art = await readArtifactSafe(name);
    contracts[name] = { address, abi: art.abi };
  }

  const out = { network: networkName, chainId, contracts };
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.log(`✓ Wrote ${outPath}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
