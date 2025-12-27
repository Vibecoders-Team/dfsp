import secrets
import time
import uuid
from collections.abc import Callable

import httpx
import pytest

from ..signer import EIP712Signer

pytestmark = pytest.mark.e2e


# =========================
# Вспомогательные функции
# =========================


def setup_user_with_files(client: httpx.Client, file_count: int) -> tuple[int, dict, EIP712Signer]:
    """
    Регистрирует нового пользователя, линкует Telegram chat_id
    и создаёт file_count файлов через /files + /meta-tx/submit.

    Возвращает:
      (chat_id, auth_headers, signer)
    """
    signer = EIP712Signer("0x" + secrets.token_hex(32))
    chat_id = secrets.randbelow(1_000_000_000)

    # Регистрация юзера
    challenge_resp = client.post("/auth/challenge")
    assert challenge_resp.status_code == 200
    signature, typed_data = signer.sign(challenge_resp.json()["nonce"])
    register_payload = {
        "eth_address": signer.address,
        "challenge_id": challenge_resp.json()["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": f"Bot Test User {chat_id}",
        "rsa_public": "test_rsa_key",
    }
    register_resp = client.post("/auth/register", json=register_payload)
    assert register_resp.status_code == 200
    auth_headers = {"Authorization": f"Bearer {register_resp.json()['access']}"}

    # Линкуем Telegram chat_id
    link_start_resp = client.post("/tg/link-start", json={"chat_id": chat_id})
    assert link_start_resp.status_code == 200
    client.post(
        "/tg/link-complete",
        json={
            "link_token": link_start_resp.json()["link_token"],
            "wallet_address": signer.address,
        },
        headers=auth_headers,
    )

    # Создаём файлы
    for i in range(file_count):
        file_payload = {
            "fileId": "0x" + secrets.token_hex(32),
            "name": f"test_file_{i}.txt",
            "size": 100 + i,
            "mime": "text/plain",
            "cid": "Qm" + secrets.token_hex(22),
            "checksum": "0x" + secrets.token_hex(32),
        }
        prepare_resp = client.post("/files", json=file_payload, headers=auth_headers)
        assert prepare_resp.status_code == 200
        td_file = prepare_resp.json()["typedData"]
        sig_file = signer.sign_generic_typed_data(td_file)
        exec_resp = client.post(
            "/meta-tx/submit",
            json={"request_id": str(uuid.uuid4()), "typed_data": td_file, "signature": sig_file},
        )
        assert exec_resp.status_code in (200, 202)
        time.sleep(0.5)

    return chat_id, auth_headers, signer


def setup_user_with_grants(
    client: httpx.Client,
    grant_count: int,
    pow_factory: Callable[[], dict],
) -> dict:
    """
    Создаёт grant_count файлов у grantor и расшаривает их на grantee
    через /files/{id}/share + /meta-tx/submit.
    Возвращает словарь с chat_id грантора и гранти.
    """
    grantor_chat_id, grantor_auth, grantor_signer = setup_user_with_files(client, grant_count)

    # создаём второго пользователя (grantee) и линкуем его Telegram chat_id
    grantee_signer = EIP712Signer("0x" + secrets.token_hex(32))
    grantee_chat_id = secrets.randbelow(1_000_000_000)
    challenge_resp_B = client.post("/auth/challenge")
    signature_B, typed_data_B = grantee_signer.sign(challenge_resp_B.json()["nonce"])
    register_payload_B = {
        "eth_address": grantee_signer.address,
        "challenge_id": challenge_resp_B.json()["challenge_id"],
        "signature": signature_B,
        "typed_data": typed_data_B,
        "display_name": "Bot Grantee",
        "rsa_public": "test_rsa_key",
    }
    register_resp_B = client.post("/auth/register", json=register_payload_B)
    assert register_resp_B.status_code == 200
    grantee_auth = {"Authorization": f"Bearer {register_resp_B.json()['access']}"}
    link_start_resp_B = client.post("/tg/link-start", json={"chat_id": grantee_chat_id})
    assert link_start_resp_B.status_code == 200
    client.post(
        "/tg/link-complete",
        json={
            "link_token": link_start_resp_B.json()["link_token"],
            "wallet_address": grantee_signer.address,
        },
        headers=grantee_auth,
    )

    # Берём файлы grantor'а через /bot/files
    files_resp = client.get("/bot/files", headers={"X-TG-Chat-Id": str(grantor_chat_id)})
    assert files_resp.status_code == 200
    created_files_data = files_resp.json()
    assert "files" in created_files_data
    created_files = created_files_data["files"]
    assert len(created_files) >= grant_count

    # Шарим каждый файл grantee
    for i in range(grant_count):
        file_id_hex = created_files[i]["id_hex"]
        file_id_bytes = "0x" + file_id_hex

        share_body = {
            "users": [grantee_signer.address],
            "ttl_days": 7,
            "max_dl": 3,
            "encK_map": {grantee_signer.address: "YQ=="},
            "request_id": str(uuid.uuid4()),
        }

        full_headers = {**grantor_auth, **pow_factory()}
        prepare_grant_resp = client.post(f"/files/{file_id_bytes}/share", json=share_body, headers=full_headers)
        assert prepare_grant_resp.status_code == 200, f"Grant prepare failed: {prepare_grant_resp.text}"

        td_grant = prepare_grant_resp.json()["typedData"]
        sig_grant = grantor_signer.sign_generic_typed_data(td_grant)
        exec_grant_resp = client.post(
            "/meta-tx/submit",
            json={"request_id": str(uuid.uuid4()), "typed_data": td_grant, "signature": sig_grant},
        )
        assert exec_grant_resp.status_code == 200
        time.sleep(0.5)

    return {"grantor": {"chat_id": grantor_chat_id}, "grantee": {"chat_id": grantee_chat_id}}


def _register_user_for_bot_jwt(client: httpx.Client) -> tuple[EIP712Signer, dict]:
    """
    Быстрая регистрация пользователя для JWT-бот-эндпоинтов (без Telegram линковки).
    """
    signer = EIP712Signer("0x" + secrets.token_hex(32))
    challenge_resp = client.post("/auth/challenge")
    assert challenge_resp.status_code == 200
    signature, typed_data = signer.sign(challenge_resp.json()["nonce"])
    register_payload = {
        "eth_address": signer.address,
        "challenge_id": challenge_resp.json()["challenge_id"],
        "signature": signature,
        "typed_data": typed_data,
        "display_name": "Bot JWT User",
        "rsa_public": "test_rsa_key",
    }
    register_resp = client.post("/auth/register", json=register_payload)
    assert register_resp.status_code == 200
    auth_headers = {"Authorization": f"Bearer {register_resp.json()['access']}"}
    return signer, auth_headers


# =========================
# Тесты для /bot/me
# =========================


def test_bot_me_linked_chat_id(client: httpx.Client):
    chat_id, _, signer = setup_user_with_files(client, 1)
    headers = {"X-TG-Chat-Id": str(chat_id)}

    resp = client.get("/bot/me", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["address"].lower() == signer.address.lower()
    assert "display_name" in data


def test_bot_me_no_header(client: httpx.Client):
    resp = client.get("/bot/me")
    # Поведение выравниваем с /bot/files: отсутствие заголовка -> 400
    assert resp.status_code == 400


def test_bot_me_unlinked_chat_id(client: httpx.Client):
    headers = {"X-TG-Chat-Id": "999999999"}
    resp = client.get("/bot/me", headers=headers)
    assert resp.status_code == 404


# =========================
# Тесты для /bot/files
# =========================


def test_get_files_successfully(client: httpx.Client):
    chat_id, _, _ = setup_user_with_files(client, 3)
    headers = {"X-TG-Chat-Id": str(chat_id)}

    response = client.get("/bot/files", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    assert len(data["files"]) == 3


def test_get_files_with_pagination(client: httpx.Client):
    chat_id, _, _ = setup_user_with_files(client, 5)
    headers = {"X-TG-Chat-Id": str(chat_id)}

    response1 = client.get("/bot/files?limit=3", headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["files"]) == 3
    cursor = data1["cursor"]
    assert cursor is not None

    # используем курсор как есть
    response2 = client.get(f"/bot/files?limit=3&cursor={cursor}", headers=headers)
    assert response2.status_code == 200, f"Failed on second page: {response2.text}"
    data2 = response2.json()
    assert len(data2["files"]) == 2


def test_get_files_no_header(client: httpx.Client):
    response = client.get("/bot/files")
    assert response.status_code == 400


def test_get_files_unlinked_chat_id(client: httpx.Client):
    headers = {"X-TG-Chat-Id": "999999999"}
    response = client.get("/bot/files", headers=headers)
    assert response.status_code == 404


def test_get_files_invalid_cursor(client: httpx.Client):
    chat_id, _, _ = setup_user_with_files(client, 1)
    headers = {"X-TG-Chat-Id": str(chat_id)}
    response = client.get("/bot/files?cursor=invalid-date-format", headers=headers)
    assert response.status_code == 400


# =========================
# Тесты для /bot/grants
# =========================


def test_get_outgoing_grants(client: httpx.Client, pow_header_factory: Callable):
    setup_data = setup_user_with_grants(client, 2, pow_header_factory)
    grantor_chat_id = setup_data["grantor"]["chat_id"]
    headers = {"X-TG-Chat-Id": str(grantor_chat_id)}

    response = client.get("/bot/grants?direction=out", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "grants" in data
    assert len(data["grants"]) == 2


def test_get_incoming_grants(client: httpx.Client, pow_header_factory: Callable):
    setup_data = setup_user_with_grants(client, 1, pow_header_factory)
    grantee_chat_id = setup_data["grantee"]["chat_id"]
    headers = {"X-TG-Chat-Id": str(grantee_chat_id)}

    response = client.get("/bot/grants?direction=in", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "grants" in data
    assert len(data["grants"]) == 1


def test_grants_pagination(client: httpx.Client, pow_header_factory: Callable):
    setup_data = setup_user_with_grants(client, 5, pow_header_factory)
    grantor_chat_id = setup_data["grantor"]["chat_id"]
    headers = {"X-TG-Chat-Id": str(grantor_chat_id)}

    response1 = client.get("/bot/grants?direction=out&limit=3", headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1["grants"]) == 3
    cursor = data1["cursor"]
    assert cursor is not None

    response2 = client.get(f"/bot/grants?direction=out&limit=3&cursor={cursor}", headers=headers)
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["grants"]) == 2


def test_grants_invalid_direction(client: httpx.Client):
    headers = {"X-TG-Chat-Id": "12345"}
    response = client.get("/bot/grants?direction=sideways", headers=headers)
    assert response.status_code == 400


# =========================
# Тесты для /bot/verify/{fileId}
# =========================


def test_bot_verify_existing_file(client: httpx.Client):
    chat_id, _, _ = setup_user_with_files(client, 1)
    headers = {"X-TG-Chat-Id": str(chat_id)}

    files_resp = client.get("/bot/files", headers=headers)
    assert files_resp.status_code == 200
    files_data = files_resp.json()
    assert len(files_data["files"]) == 1
    file_hex = files_data["files"][0]["id_hex"]
    file_id = "0x" + file_hex

    verify_resp = client.get(f"/bot/verify/{file_id}")
    assert verify_resp.status_code == 200
    body = verify_resp.json()

    assert set(body.keys()) == {"onchain_ok", "offchain_ok", "match", "lastAnchorTx"}
    assert body["offchain_ok"] is True
    # Файл может быть в блокчейне, если он был заанкорен, поэтому проверяем только структуру
    assert isinstance(body["onchain_ok"], bool)
    assert isinstance(body["match"], bool)
    # lastAnchorTx может быть None или строкой с хешем транзакции
    assert body["lastAnchorTx"] is None or isinstance(body["lastAnchorTx"], str)


def test_bot_verify_invalid_file_id(client: httpx.Client):
    resp = client.get("/bot/verify/0x1234")
    assert resp.status_code == 400


def test_bot_verify_not_found(client: httpx.Client):
    random_id = "0x" + ("ab" * 32)
    resp = client.get(f"/bot/verify/{random_id}")
    assert resp.status_code == 404


# =========================
# Тесты для /bot/action-intents
# =========================


def test_action_intent_create_and_consume(client: httpx.Client):
    """
    Создаём интент через POST /bot/action-intents и потребляем его через
    POST /bot/action-intents/consume тем же пользователем.
    """
    signer, headers = _register_user_for_bot_jwt(client)

    create_body = {
        "type": "share_file",
        "params": {"foo": "bar", "n": 42},
    }
    r_create = client.post("/bot/action-intents", json=create_body, headers=headers)
    assert r_create.status_code == 200, r_create.text
    data = r_create.json()
    assert "state" in data
    assert "expires_at" in data
    state = data["state"]

    r_consume = client.post(
        "/bot/action-intents/consume",
        json={"state": state},
        headers=headers,
    )
    assert r_consume.status_code == 200, r_consume.text
    consumed = r_consume.json()
    assert consumed["type"] == "share_file"
    assert consumed["params"]["foo"] == "bar"
    assert consumed["params"]["n"] == 42


def test_action_intent_wrong_owner_forbidden(client: httpx.Client):
    """
    Интент нельзя потребить под другим пользователем.
    """
    signer_a, headers_a = _register_user_for_bot_jwt(client)
    signer_b, headers_b = _register_user_for_bot_jwt(client)

    r_create = client.post(
        "/bot/action-intents",
        json={"type": "x", "params": {"a": 1}},
        headers=headers_a,
    )
    assert r_create.status_code == 200
    state = r_create.json()["state"]

    r_consume = client.post(
        "/bot/action-intents/consume",
        json={"state": state},
        headers=headers_b,
    )
    assert r_consume.status_code == 403
    assert "not_owner" in r_consume.text


def test_action_intent_double_consume_fails(client: httpx.Client):
    """
    Повторное потребление того же state запрещено (intent_already_used).
    """
    signer, headers = _register_user_for_bot_jwt(client)

    r_create = client.post(
        "/bot/action-intents",
        json={"type": "one_shot", "params": {}},
        headers=headers,
    )
    assert r_create.status_code == 200
    state = r_create.json()["state"]

    r_first = client.post(
        "/bot/action-intents/consume",
        json={"state": state},
        headers=headers,
    )
    assert r_first.status_code == 200

    r_second = client.post(
        "/bot/action-intents/consume",
        json={"state": state},
        headers=headers,
    )
    assert r_second.status_code == 400
    assert "intent_already_used" in r_second.text
