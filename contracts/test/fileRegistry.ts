import {ethers} from "hardhat";
import {expect} from "chai";

describe("FileRegistry", () => {
    it("owner can updateCid; others cannot", async () => {
        const [fwdOwner, alice, bob] = await ethers.getSigners();

        const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
        const fwd = await Fwd.deploy();
        await fwd.waitForDeployment();

        const Reg = await ethers.getContractFactory("FileRegistry");
        const reg = await Reg.connect(fwdOwner).deploy(await fwd.getAddress());
        await reg.waitForDeployment();

        const fid = ethers.id("f1");
        await reg.connect(alice).register(fid, "cid1", ethers.id("chk1"), 1, "text/plain");

        await expect(
            reg.connect(bob).updateCid(fid, "cid2", ethers.id("chk2"), 2, "text/plain")
        ).to.be.revertedWithCustomError(reg, "NotOwner");

        await reg.connect(alice).updateCid(fid, "cid2", ethers.id("chk2"), 2, "text/plain");
        const meta = await reg.metaOf(fid);
        expect(meta.cid).to.eq("cid2");
    });
});
