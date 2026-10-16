"""
Tests de la récupération de compte, de la normalisation des emails,
et de quelques garde-fous divers.
"""
import sys
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from helpers import (
    activation_payload, fake_salt_b64, fake_private_bundle_b64,
    fake_recovery_code, fake_recovery_code_hash,
)


def activate(client, seeded, email, password="MotDePasse123xy", recovery_code=None):
    token = seeded[email]
    client.post("/api/auth/verify-invitation", json={"email": email, "token": token})
    payload = activation_payload(email, token, password)
    if recovery_code:
        payload["recoveryCodeHash"] = fake_recovery_code_hash(recovery_code)
    r = client.post("/api/auth/activate-account", json=payload)
    assert r.status_code == 200, r.get_json()


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_email_is_normalized_case_insensitively(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy").get_json()
    headers = auth_header(admin["access_token"])

    r = client.post("/api/admin/users", headers=headers, json={
        "nom": "Test", "prenom": "Case", "email": "Nouveau@Test.LOCAL",
        "poste_administratif": "Agent", "niveau_id": "NIV-005", "structure_id": "STR-008",
    })
    assert r.status_code == 201

    # Correctif : la même adresse, dans une autre casse, doit être
    # reconnue comme un doublon.
    r2 = client.post("/api/admin/users", headers=headers, json={
        "nom": "Test2", "prenom": "Case2", "email": "nouveau@test.local",
        "poste_administratif": "Agent", "niveau_id": "NIV-005", "structure_id": "STR-008",
    })
    assert r2.status_code == 409


def test_recovery_flow_allows_password_reset_and_revokes_old_token(client, seeded):
    code = fake_recovery_code()
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy", recovery_code=code)

    old = login(client, "agent-rh@test.local", "AgentPass2026xy").get_json()

    r = client.post("/api/auth/forgot-password/verify", json={
        "email": "agent-rh@test.local", "recoveryCode": code
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["cle_privee_chiffree_recovery"] is not None

    r = client.post("/api/auth/forgot-password/reset", json={
        "email": "agent-rh@test.local", "recoveryCode": code,
        "newPassword": "ApresRecovery2026",
        "encryptedPrivateKey": fake_private_bundle_b64(), "salt": fake_salt_b64(),
        "recoveryEncryptedPrivateKey": fake_private_bundle_b64(),
        "recoverySalt": fake_salt_b64(),
        "recoveryCodeHash": fake_recovery_code_hash("UN-AUTRE-CODE-XXXX-YYYY"),
    })
    assert r.status_code == 200

    # Le nouveau mot de passe fonctionne.
    r = login(client, "agent-rh@test.local", "ApresRecovery2026")
    assert r.status_code == 200

    # L'ANCIEN token (émis avant la réinitialisation) est révoqué.
    r = client.get("/api/files", headers=auth_header(old["access_token"]))
    assert r.status_code == 401

    # L'ancien code de récupération est désormais invalide (à usage unique).
    r = client.post("/api/auth/forgot-password/verify", json={
        "email": "agent-rh@test.local", "recoveryCode": code
    })
    assert r.status_code == 404


def test_wrong_recovery_code_is_rejected(client, seeded):
    code = fake_recovery_code()
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy", recovery_code=code)

    r = client.post("/api/auth/forgot-password/verify", json={
        "email": "agent-rh@test.local", "recoveryCode": "CECI-EST-FAUX-00000-00000"
    })
    assert r.status_code == 404


def test_invalid_public_key_is_rejected_at_activation(client, seeded):
    email = "admin@plateforme.local"
    token = seeded[email]
    client.post("/api/auth/verify-invitation", json={"email": email, "token": token})

    payload = activation_payload(email, token)
    payload["publicKey"] = "BBBB"  # bien trop court pour une clé SPKI RSA-2048

    r = client.post("/api/auth/activate-account", json=payload)
    assert r.status_code == 400


def test_rate_limit_blocks_repeated_login_failures(app, client, seeded):
    import os
    os.environ["RATELIMIT_ENABLED"] = "1"

    # Recrée l'app avec le rate-limit actif (la fixture `app` l'a
    # désactivé pour les autres tests).
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app import create_app
    limited_app = create_app()
    limited_client = limited_app.test_client()

    codes = []
    for i in range(15):
        r = limited_client.post("/api/auth/login", json={
            "email": "inexistant@test.local", "password": f"x{i}"
        })
        codes.append(r.status_code)

    assert 429 in codes

    os.environ["RATELIMIT_ENABLED"] = "0"
