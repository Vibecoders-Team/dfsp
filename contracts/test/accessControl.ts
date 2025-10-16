import {ethers} from "hardhat";
import {expect} from "chai";

describe("AccessControlDFSP", () => {
    it("grant/useOnce/revoke/expiry", async () => {
        const [fwdOwner, grantor, grantee] = await ethers.getSigners();

        const Fwd = await ethers.getContractFactory("src/MinimalForwarder.sol:MinimalForwarder");
        const fwd = await Fwd.deploy();
        await fwd.waitForDeployment();

        const AC = await ethers.getContractFactory("AccessControlDFSP");
        const ac = await AC.deploy(await fwd.getAddress());
        await ac.waitForDeployment();

        const fid = ethers.id("f1");
        const ttl = 3600;
        const cap = await ac.connect(grantor).grant.staticCall(fid, await grantee.getAddress(), ttl, 2);
        await ac.connect(grantor).grant(fid, await grantee.getAddress(), ttl, 2);

        expect(await ac.canDownload(await grantee.getAddress(), fid)).to.eq(true);

        await ac.connect(grantee).useOnce(cap);
        const g = await ac.grants(cap);
        expect(g.used).to.eq(1);

        await ac.connect(grantor).revoke(cap);
        await expect(ac.connect(grantee).useOnce(cap)).to.be.revertedWithCustomError(ac, "RevokedGrant");
    });
});
