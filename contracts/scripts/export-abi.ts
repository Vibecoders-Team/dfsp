// scripts/export-abi.ts
import { writeFileSync, mkdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import hre from "hardhat";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  // FQN только для форвардера; остальные имена уникальны
  const entries = [
    { fq: "src/MinimalForwarder.sol:MinimalForwarder", out: "MinimalForwarder" },
    { fq: "FileRegistry", out: "FileRegistry" },
    { fq: "AccessControlDFSP", out: "AccessControlDFSP" },
    { fq: "DFSPAnchoring", out: "DFSPAnchoring" },
  ];

  const outDir = path.join(__dirname, "../artifacts-abi");
  mkdirSync(outDir, { recursive: true });

  for (const e of entries) {
    const art = await hre.artifacts.readArtifact(e.fq);
    writeFileSync(path.join(outDir, `${e.out}.abi.json`), JSON.stringify(art.abi, null, 2));
    console.log("ABI ->", e.out);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
