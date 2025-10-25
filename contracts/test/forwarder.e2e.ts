// test/forwarder.e2e.ts
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

const selectorOf = (signature: string) => ethers.id(signature).slice(0, 10);

// ✅ ethers v6: forwarder.execute.staticCall(...)
async function expectForwardedRevert(
  forwarder: any,
  req: any,
  sig: string,
  expectedSelector: string
) {
  const res = await forwarder.execute.staticCall(req, sig); // v6 style
  // OZ MinimalForwarder: function execute(...) returns (bool success, bytes memory returndata)
  const ok: boolean = (res as any).success ?? res[0];
  const ret: string = (res as any).returndata ?? res[1];

  expect(ok, "forwarded call should fail inside target").to.eq(false);

  const gotSel = ethers.hexlify(ret).slice(0, 10);
  expect(gotSel, "unexpected revert selector").to.eq(expectedSelector);
}

describe("ERC-2771 meta-tx -> FileRegistry", () => {
  it("register via MinimalForwarder", async () => {
    const [user] = await ethers.getSigners();

    const Forwarder = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const forwarder = await Forwarder.deploy();
    await forwarder.waitForDeployment();

    const FileRegistry = await ethers.getContractFactory("FileRegistry");
    const registry = await FileRegistry.deploy(await forwarder.getAddress());
    await registry.waitForDeployment();

    const fileId = ethers.id("demo-file-1");
    const cid = "bafy...demo";
    const checksum = ethers.id("ciphertext-blob");
    const size = 123456;
    const mime = "application/octet-stream";

    const data = registry.interface.encodeFunctionData("register", [
      fileId,
      cid,
      checksum,
      size,
      mime,
    ]);

    const nonce = await forwarder.getNonce(await user.getAddress());
    const request = {
      from: await user.getAddress(),
      to: await registry.getAddress(),
      value: 0,
      gas: 1_000_000,
      nonce,
      data,
    };

    const domain = {
      name: "MinimalForwarder",
      version: "0.0.1",
      chainId: (await ethers.provider.getNetwork()).chainId,
      verifyingContract: await forwarder.getAddress(),
    };

    const signature = await user.signTypedData(domain, types, request);
    expect(await forwarder.verify(request, signature)).to.eq(true);

    const tx = await forwarder.execute(request, signature);
    await tx.wait();

    const meta = await registry.metaOf(fileId);
    expect(meta.owner).to.eq(await user.getAddress());
    expect(meta.cid).to.eq(cid);
  });

  it("updateCid via forwarder: owner succeeds, non-owner fails inside target (NotOwner)", async () => {
    const [owner, other] = await ethers.getSigners();

    const Forwarder = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
    const forwarder = await Forwarder.deploy();
    await forwarder.waitForDeployment();

    const FileRegistry = await ethers.getContractFactory("FileRegistry");
    const registry = await FileRegistry.deploy(await forwarder.getAddress());
    await registry.waitForDeployment();

    const fileId = ethers.id("meta-update-1");

    // Direct register
    await registry.connect(owner).register(fileId, "cid0", ethers.id("chk0"), 1, "text/plain");

    // --- Owner updates via forwarder (ok) ---
    const updateData = registry.interface.encodeFunctionData("updateCid", [
      fileId,
      "cid1",
      ethers.id("chk1"),
      2,
      "text/plain",
    ]);
    {
      const nonce = await forwarder.getNonce(await owner.getAddress());
      const req = {
        from: await owner.getAddress(),
        to: await registry.getAddress(),
        value: 0,
        gas: 1_000_000,
        nonce,
        data: updateData,
      };
      const domain = {
        name: "MinimalForwarder",
        version: "0.0.1",
        chainId: (await ethers.provider.getNetwork()).chainId,
        verifyingContract: await forwarder.getAddress(),
      };
      const sig = await owner.signTypedData(domain, types, req);
      expect(await forwarder.verify(req, sig)).to.eq(true);
      await (await forwarder.execute(req, sig)).wait();
    }
    expect((await registry.metaOf(fileId)).cid).to.eq("cid1");

    // --- Non-owner via forwarder (должно зафейлиться внутри цели) ---
    const updateData2 = registry.interface.encodeFunctionData("updateCid", [
      fileId,
      "cid2",
      ethers.id("chk2"),
      3,
      "text/plain",
    ]);
    const nonce2 = await forwarder.getNonce(await other.getAddress());
    const req2 = {
      from: await other.getAddress(),
      to: await registry.getAddress(),
      value: 0,
      gas: 1_000_000,
      nonce: nonce2,
      data: updateData2,
    };
    const domain2 = {
      name: "MinimalForwarder",
      version: "0.0.1",
      chainId: (await ethers.provider.getNetwork()).chainId,
      verifyingContract: await forwarder.getAddress(),
    };
    const sig2 = await other.signTypedData(domain2, types, req2);
    expect(await forwarder.verify(req2, sig2)).to.eq(true);

    // Проверяем revert через staticCall + селектор кастомной ошибки
    await expectForwardedRevert(forwarder, req2, sig2, selectorOf("NotOwner()"));

    // Реальный execute (не ревертит сам форвардер) — состояние не меняется
    await (await forwarder.execute(req2, sig2)).wait();
    expect((await registry.metaOf(fileId)).cid).to.eq("cid1");
  });
});
