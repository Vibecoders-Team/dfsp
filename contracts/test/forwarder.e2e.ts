import {ethers} from "hardhat";
import {expect} from "chai";

const types = {
    ForwardRequest: [
        {name: "from", type: "address"},
        {name: "to", type: "address"},
        {name: "value", type: "uint256"},
        {name: "gas", type: "uint256"},
        {name: "nonce", type: "uint256"},
        {name: "data", type: "bytes"}
    ]
};

describe("ERC-2771 meta-tx -> FileRegistry", () => {
    it("register via MinimalForwarder", async () => {
        const [user] = await ethers.getSigners();

        const Forwarder = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
        const forwarder = await Forwarder.deploy();
        await forwarder.waitForDeployment();

        const FileRegistry = await ethers.getContractFactory("FileRegistry");
        const registry = await FileRegistry.deploy(await forwarder.getAddress());
        await registry.waitForDeployment();

        const fileId = ethers.id("demo-file-1"); // keccak256
        const cid = "bafy...demo";
        const checksum = ethers.id("ciphertext-blob");
        const size = 123456;
        const mime = "application/octet-stream";

        const data = registry.interface.encodeFunctionData("register", [fileId, cid, checksum, size, mime]);

        const nonce = await forwarder.getNonce(await user.getAddress());
        const request = {
            from: await user.getAddress(),
            to: await registry.getAddress(),
            value: 0,
            gas: 1_000_000,
            nonce,
            data
        };

        const domain = {
            name: "MinimalForwarder",
            version: "0.0.1",
            chainId: (await ethers.provider.getNetwork()).chainId,
            verifyingContract: await forwarder.getAddress()
        };

        const signature = await user.signTypedData(domain, types, request);
        expect(await forwarder.verify(request, signature)).to.eq(true);

        const tx = await forwarder.execute(request, signature);
        await tx.wait();

        const meta = await registry.metaOf(fileId);
        expect(meta.owner).to.eq(await user.getAddress());
        expect(meta.cid).to.eq(cid);
    });
});
