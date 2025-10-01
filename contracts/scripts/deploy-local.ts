import { writeFileSync, mkdirSync } from "fs";
import path from "path";
import { ethers } from "hardhat";

async function main() {
  const [deployer] = await ethers.getSigners();

  const Forwarder = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
  const forwarder = await Forwarder.deploy();
  await forwarder.waitForDeployment();

  const FileRegistry = await ethers.getContractFactory("FileRegistry");
  const registry = await FileRegistry.deploy(await forwarder.getAddress());
  await registry.waitForDeployment();

  const Access = await ethers.getContractFactory("AccessControlDFSP");
  const access = await Access.deploy(await forwarder.getAddress());
  await access.waitForDeployment();

  const Anchoring = await ethers.getContractFactory("DFSPAnchoring");
  const anchoring = await Anchoring.deploy(await deployer.getAddress());
  await anchoring.waitForDeployment();

  const chainId = (await ethers.provider.getNetwork()).chainId.toString();

  const outDir = path.join(__dirname, "../deploy");
  mkdirSync(outDir, { recursive: true });
  const cfg = {
    chainId,
    verifyingContracts: {
      MinimalForwarder: await forwarder.getAddress(),
      FileRegistry: await registry.getAddress(),
      AccessControlDFSP: await access.getAddress(),
      DFSPAnchoring: await anchoring.getAddress()
    },
    domain: { name: "MinimalForwarder", version: "0.0.1" }
  };
  writeFileSync(path.join(outDir, "chain-config.json"), JSON.stringify(cfg, null, 2));

  // .env для backend/frontend (локалка)
  const env = [
    `RPC_URL=http://chain:8545`,
    `CONTRACT_FORWARDER=${await forwarder.getAddress()}`,
    `CONTRACT_FILE_REGISTRY=${await registry.getAddress()}`,
    `CONTRACT_ACCESS_CONTROL=${await access.getAddress()}`,
    `CONTRACT_ANCHORING=${await anchoring.getAddress()}`
  ].join("\n");
  writeFileSync(path.join(outDir, ".env.local"), env + "\n");

  console.log("Deployed:", cfg);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
