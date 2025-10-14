// contracts/scripts/deploy-local.ts
import { writeFileSync, mkdirSync } from "fs";
import path from "path";
import { ethers, artifacts } from "hardhat";

const FWD_FQN = "src/MinimalForwarder.sol:MinimalForwarder";

function writeJSON(p: string, obj: any) {
  mkdirSync(path.dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(obj, null, 2));
}

async function main() {
  const [deployer] = await ethers.getSigners();

  const Forwarder = await ethers.getContractFactory(FWD_FQN);
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

  // --- 1) как у тебя было: файлы для фронта ---
  const outDir = path.join(__dirname, "../deploy");
  mkdirSync(outDir, { recursive: true });
  const cfg = {
    chainId,
    verifyingContracts: {
      MinimalForwarder: await forwarder.getAddress(),
      FileRegistry: await registry.getAddress(),
      AccessControlDFSP: await access.getAddress(),
      DFSPAnchoring: await anchoring.getAddress(),
    },
    domain: { name: "MinimalForwarder", version: "0.0.1" },
  };
  writeJSON(path.join(outDir, "chain-config.json"), cfg);

  const env = [
    `RPC_URL=http://chain:8545`,
    `CONTRACT_FORWARDER=${await forwarder.getAddress()}`,
    `CONTRACT_FILE_REGISTRY=${await registry.getAddress()}`,
    `CONTRACT_ACCESS_CONTROL=${await access.getAddress()}`,
    `CONTRACT_ANCHORING=${await anchoring.getAddress()}`,
  ].join("\n");
  writeFileSync(path.join(outDir, ".env.local"), env + "\n");

  // --- 2) новый файл для backend: адрес + ABI, путь из DEPLOY_OUT ---
  const deployOut = process.env.DEPLOY_OUT || path.join(__dirname, "../out/deployment.localhost.json");

  const regAbi = (await artifacts.readArtifact("FileRegistry")).abi;
  const accAbi = (await artifacts.readArtifact("AccessControlDFSP")).abi;
  const ancAbi = (await artifacts.readArtifact("DFSPAnchoring")).abi;
  const fwdAbi = (await artifacts.readArtifact(FWD_FQN)).abi;

  const backendOut = {
    chainId,
    contracts: {
      FileRegistry:        { address: await registry.getAddress(),   abi: regAbi },
      AccessControlDFSP:   { address: await access.getAddress(),     abi: accAbi },
      DFSPAnchoring:       { address: await anchoring.getAddress(),  abi: ancAbi },
      MinimalForwarder:    { address: await forwarder.getAddress(),  abi: fwdAbi },
    },
  };
  mkdirSync(path.dirname(deployOut), { recursive: true });
  writeFileSync(deployOut, JSON.stringify(backendOut, null, 2));

  console.log("Deployed:\n", JSON.stringify(backendOut, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
