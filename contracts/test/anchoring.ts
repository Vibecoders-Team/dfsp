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
});
