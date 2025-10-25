import pytest
from web3 import Web3

from app.deps import get_chain


@pytest.mark.e2e
def test_capid_prediction_matches_event():
    chain = get_chain()
    ac = chain.get_access_control()

    accounts = chain.w3.eth.accounts
    assert len(accounts) >= 3, "Need at least 3 accounts on local chain"

    grantor = accounts[1]
    grantee = accounts[2]

    file_id = Web3.keccak(text="capid-test-1")

    start_nonce = chain.read_grant_nonce(grantor)
    expected = chain.predict_cap_id(grantor, grantee, file_id, nonce=start_nonce, offset=0)

    txh = ac.functions.grant(file_id, grantee, 60, 1).transact({"from": grantor})
    rcpt = chain.w3.eth.wait_for_transaction_receipt(txh)

    # decode event
    evts = ac.events.Granted().process_receipt(rcpt)
    assert evts and len(evts) == 1
    cap_from_event = evts[0]["args"]["capId"]

    assert cap_from_event == expected

    # also storage sanity
    g = ac.functions.grants(expected).call()
    # createdAt is index 6 in struct, but web3.py returns tuple
    assert g[6] != 0
