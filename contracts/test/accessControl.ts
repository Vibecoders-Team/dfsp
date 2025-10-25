import { ethers } from "hardhat";
import { expect } from "chai";

const types = {
  ForwardRequest: [
    { name: "from", type: "address" },
    { name: "to", type: "address" },
    { name: "value", type: "uint256" },
    { name: "gas", type: "uint256" },
    { name: "nonce", type: "uint256" },
    { name: "data", type: "bytes" },
  ],
};

async function signAndExecute(forwarder: any, signer: any, to: string, data: string, gas = 1_000_000n) {
  const nonce = await forwarder.getNonce(await signer.getAddress());
  const request = {
    from: await signer.getAddress(),
    to,
    value: 0,
    gas,
    nonce,
    data,
  };
  const domain = {
    name: "MinimalForwarder",
    version: "0.0.1",
    chainId: (await ethers.provider.getNetwork()).chainId,
    verifyingContract: await forwarder.getAddress(),
  };
  const signature = await signer.signTypedData(domain, types as any, request);
  expect(await forwarder.verify(request, signature)).to.eq(true);
  const tx = await forwarder.execute(request, signature);
  return tx.wait();
}

function keccakAbiEncode(grantor: string, grantee: string, fileId: string, nonce: bigint): string {
  const abi = ethers.AbiCoder.defaultAbiCoder();
  const encoded = abi.encode(["address", "address", "bytes32", "uint256"], [grantor, grantee, fileId, nonce]);
  return ethers.keccak256(encoded);
}

describe("AccessControlDFSP - extended", () => {
  // Предохранитель: даже если тест упадёт, вернём майнинг в норму
  afterEach(async () => {
    try {
      await ethers.provider.send("evm_setAutomine", [true]);
      // На всякий случай добьём пустой блок — полезно, если что-то ждало майнинга
      await ethers.provider.send("evm_mine", []);
    } catch {
      // игнор
    }
  });

  it("useOnce race in the same block: second reverts ExhaustedGrant", async () => {
  const [fwdOwner, grantor, grantee] = await ethers.getSigners();

  const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
  const fwd = await Fwd.deploy();
  await fwd.waitForDeployment();

  const AC = await ethers.getContractFactory("AccessControlDFSP");
  const ac = await AC.deploy(await fwd.getAddress());
  await ac.waitForDeployment();

  const fid = ethers.id("file-race");
  const cap = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), 3600, 1);
  await ac.connect(grantor).grant(fid, await grantee.getAddress(), 3600, 1);

  await ethers.provider.send("evm_setAutomine", [false]);

  try {
    // Берём базовый nonce и выставляем явные значения
    const baseNonce = await ethers.provider.getTransactionCount(
      await grantee.getAddress(),
      "pending"
    );

    const tx1 = await ac.connect(grantee).useOnce(cap, {
      nonce: baseNonce,
      // подстрахуемся явным лимитом газа
      gasLimit: 300_000
    });
    const tx2 = await ac.connect(grantee).useOnce(cap, {
      nonce: baseNonce + 1,
      gasLimit: 300_000
    });

    // В один блок
    await ethers.provider.send("evm_mine", []);

    // НЕ используем wait(); берём квитанции напрямую
    const r1 = await ethers.provider.getTransactionReceipt(tx1.hash);
    const r2 = await ethers.provider.getTransactionReceipt(tx2.hash);

    // Оба должны быть включены в только что добытый блок
    expect(r1).to.not.equal(null);
    expect(r2).to.not.equal(null);

    // Первый должен быть успешным
    expect(Number(r1!.status)).to.eq(1);

    // Второй должен быть неуспешным (реверт)
    expect(Number(r2!.status)).to.eq(0);

    // Сообщение об ошибке у второй проверим через callStatic для той же inputs,
    // чтобы не зависеть от текста из провайдера
    await expect(ac.connect(grantee).useOnce.staticCall(cap))
      .to.be.revertedWithCustomError(ac, "ExhaustedGrant");

    // used == 1
    const g = await ac.grants(cap);
    expect(g.used).to.eq(1);
  } finally {
    await ethers.provider.send("evm_setAutomine", [true]);
    await ethers.provider.send("evm_mine", []);
  }
});


  it("ttl=0 results in ExpiredGrant on use", async () => {
    const [fwdOwner, grantor, grantee] = await ethers.getSigners();

    const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const fwd = await Fwd.deploy();
    await fwd.waitForDeployment();

    const AC = await ethers.getContractFactory("AccessControlDFSP");
    const ac = await AC.deploy(await fwd.getAddress());
    await ac.waitForDeployment();

    const fid = ethers.id("ttl0");
    const cap = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), 0, 2);
    await ac.connect(grantor).grant(fid, await grantee.getAddress(), 0, 2);

    await ethers.provider.send("evm_increaseTime", [1]);
    await ethers.provider.send("evm_mine", []);

    await expect(ac.connect(grantee).useOnce(cap)).to.be.revertedWithCustomError(ac, "ExpiredGrant");
  });

  it("grant with grantee=0x0 reverts InvalidGrantee", async () => {
    const [fwdOwner, grantor] = await ethers.getSigners();

    const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const fwd = await Fwd.deploy();
    await fwd.waitForDeployment();

    const AC = await ethers.getContractFactory("AccessControlDFSP");
    const ac = await AC.deploy(await fwd.getAddress());
    await ac.waitForDeployment();

    const fid = ethers.id("zero");
    await expect(ac.connect(grantor).grant(fid, ethers.ZeroAddress, 3600, 1)).to.be.revertedWithCustomError(ac, "InvalidGrantee");
  });

  it("revoke idempotent: second revoke reverts RevokedGrant", async () => {
    const [fwdOwner, grantor, grantee] = await ethers.getSigners();

    const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const fwd = await Fwd.deploy();
    await fwd.waitForDeployment();

    const AC = await ethers.getContractFactory("AccessControlDFSP");
    const ac = await AC.deploy(await fwd.getAddress());
    await ac.waitForDeployment();

    const fid = ethers.id("rev");
    const cap = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), 3600, 2);
    await ac.connect(grantor).grant(fid, await grantee.getAddress(), 3600, 2);

    await ac.connect(grantor).revoke(cap);
    await expect(ac.connect(grantor).revoke(cap)).to.be.revertedWithCustomError(ac, "RevokedGrant");
  });

  it("ERC-2771 _msgSender works for grant/useOnce/revoke and direct calls also succeed", async () => {
    const [fwdOwner, grantor, grantee] = await ethers.getSigners();

    const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const fwd = await Fwd.deploy();
    await fwd.waitForDeployment();

    const AC = await ethers.getContractFactory("AccessControlDFSP");
    const ac = await AC.deploy(await fwd.getAddress());
    await ac.waitForDeployment();

    const fid = ethers.id("meta");

    // Direct (non-forwarder) grant
    const capDirect = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), 3600, 3);
    await ac.connect(grantor).grant(fid, await grantee.getAddress(), 3600, 3);
    expect((await ac.grants(capDirect)).grantor).to.eq(await grantor.getAddress());

    // Meta-tx grant (forwarder)
    const dataGrant = ac.interface.encodeFunctionData("grant", [fid, await grantee.getAddress(), 3600, 3]);
    await signAndExecute(fwd, grantor, await ac.getAddress(), dataGrant);

    // Determinism for meta grant: compute expected cap with current nonce before call
    const fid2 = ethers.id("meta-2");
    const n2 = await ac.grantNonces(await grantor.getAddress());
    const expectedCap2 = keccakAbiEncode(await grantor.getAddress(), await grantee.getAddress(), fid2, n2);
    const dataGrant2 = ac.interface.encodeFunctionData("grant", [fid2, await grantee.getAddress(), 3600, 1]);
    await signAndExecute(fwd, grantor, await ac.getAddress(), dataGrant2);
    const g2 = await ac.grants(expectedCap2);
    expect(g2.createdAt).to.not.eq(0n);

    // Meta useOnce on expectedCap2 should increment used
    await signAndExecute(fwd, grantee, await ac.getAddress(), ac.interface.encodeFunctionData("useOnce", [expectedCap2]));
    const g2After = await ac.grants(expectedCap2);
    expect(g2After.used).to.eq(1);

    // Meta revoke and ensure revoked
    await signAndExecute(fwd, grantor, await ac.getAddress(), ac.interface.encodeFunctionData("revoke", [expectedCap2]));
    const g2Rev = await ac.grants(expectedCap2);
    expect(g2Rev.revoked).to.eq(true);
  });

  it("deterministic capId off-chain vs on-chain (direct grant)", async () => {
    const [fwdOwner, grantor, grantee] = await ethers.getSigners();

    const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const fwd = await Fwd.deploy();
    await fwd.waitForDeployment();

    const AC = await ethers.getContractFactory("AccessControlDFSP");
    const ac = await AC.deploy(await fwd.getAddress());
    await ac.waitForDeployment();

    const fid = ethers.id("det");

    const n = await ac.grantNonces(await grantor.getAddress());
    const expected = keccakAbiEncode(await grantor.getAddress(), await grantee.getAddress(), fid, n);

    const capStatic = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), 100, 1);
    expect(capStatic.toLowerCase()).to.eq(expected.toLowerCase());

    await ac.connect(grantor).grant(fid, await grantee.getAddress(), 100, 1);
    const g = await ac.grants(expected);
    expect(g.createdAt).to.not.eq(0n);
  });
});
