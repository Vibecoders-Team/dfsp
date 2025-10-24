import {ethers} from "hardhat";
import {expect} from "chai";

describe("DFSPAnchoring", () => {
    it("only owner can anchor", async () => {
        const [owner, other] = await ethers.getSigners();
        const Anch = await ethers.getContractFactory("DFSPAnchoring");
        const anch = await Anch.deploy(await owner.getAddress());
        await anch.waitForDeployment();

        await expect(anch.connect(other).anchorMerkleRoot(ethers.ZeroHash, 1)).to.be.reverted;

        await expect(anch.connect(owner).anchorMerkleRoot(ethers.ZeroHash, 1))
            .to.emit(anch, "Anchored").withArgs(ethers.ZeroHash, 1);
    });

    it("transferOwnership: only new owner can anchor", async () => {
        const [owner, newOwner, other] = await ethers.getSigners();
        const Anch = await ethers.getContractFactory("DFSPAnchoring");
        const anch = await Anch.deploy(await owner.getAddress());
        await anch.waitForDeployment();

        // Old owner can anchor
        await expect(anch.connect(owner).anchorMerkleRoot(ethers.id("root1"), 42))
            .to.emit(anch, "Anchored").withArgs(ethers.id("root1"), 42);

        // Transfer ownership
        await anch.connect(owner).transferOwnership(await newOwner.getAddress());

        // Old owner can no longer anchor
        await expect(anch.connect(owner).anchorMerkleRoot(ethers.id("root2"), 43)).to.be.reverted;

        // New owner can anchor
        await expect(anch.connect(newOwner).anchorMerkleRoot(ethers.id("root3"), 44))
            .to.emit(anch, "Anchored").withArgs(ethers.id("root3"), 44);

        // Random other cannot
        await expect(anch.connect(other).anchorMerkleRoot(ethers.id("root4"), 45)).to.be.reverted;
    });
});
