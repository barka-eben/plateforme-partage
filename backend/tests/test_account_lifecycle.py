"""
Tests du cycle de vie d'un compte : création, activation, connexion,
changement de mot de passe, désactivation, suppression.
"""
import sys
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from helpers import activation_payload, fake_salt_b64, fake_private_bundle_b64


def activate(client, seeded, email, password="MotDePasse123xy"):
    token = seeded[email]
    r = client.post("/api/auth/verify-invitation", json={"email": email, "token": token})
    assert r.status_code == 200, r.get_json()
    r = client.post("/api/auth/activate-account", json=activation_payload(email, token, password))
    assert r.status_code == 200, r.get_json()


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_activation_then_login_returns_both_public_keys(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    data = login(client, "admin@plateforme.local", "AdminPass2026xy")

    # Correctif central de l'audit : login renvoie désormais les deux
    # clés publiques (sans elles, aucun envoi de fichier n'est possible).
    assert data["cle_publique"] is not None
    assert data["cle_publique_signature"] is not None
    assert data["cle_privee_chiffree"] is not None
    assert data["pbkdf2_iterations"] == 600_000


def test_pending_account_cannot_login(client, seeded):
    r = client.post("/api/auth/login", json={
        "email": "admin@plateforme.local", "password": "peu importe"
    })
    assert r.status_code == 403


def test_activation_link_not_exposed_by_default(client, seeded):
    """
    EXPOSE_ACTIVATION_LINK_DEV n'est pas positionné dans les tests
    (cf. conftest.py) : la création d'un compte ne doit PAS renvoyer
    le lien d'activation dans la réponse JSON.
    """
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    data = login(client, "admin@plateforme.local", "AdminPass2026xy")
    headers = auth_header(data["access_token"])

    r = client.post("/api/admin/users", headers=headers, json={
        "nom": "Nouveau", "prenom": "Compte", "email": "nouveau@test.local",
        "poste_administratif": "Agent", "niveau_id": "NIV-005", "structure_id": "STR-008",
    })
    assert r.status_code == 201
    assert "lien_activation_dev" not in r.get_json()


def test_password_over_72_bytes_is_rejected_cleanly(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")

    r = client.post("/api/auth/login", json={
        "email": "admin@plateforme.local", "password": "y" * 100
    })
    # Ne doit JAMAIS être un 500 (bcrypt qui plante) : 401 propre.
    assert r.status_code == 401


def test_change_password_bumps_epoch_and_revokes_old_token(client, seeded):
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")
    data = login(client, "agent-rh@test.local", "AgentPass2026xy")
    old_token = data["access_token"]

    r = client.post("/api/auth/change-password", headers=auth_header(old_token), json={
        "current_password": "AgentPass2026xy",
        "new_password": "NouveauPass2026z",
        "encryptedPrivateKey": fake_private_bundle_b64(),
        "salt": fake_salt_b64(),
    })
    assert r.status_code == 200

    # L'ancien token doit être rejeté immédiatement (correctif : jwt_epoch).
    r = client.get("/api/files", headers=auth_header(old_token))
    assert r.status_code == 401

    # Le nouveau mot de passe doit fonctionner.
    data2 = login(client, "agent-rh@test.local", "NouveauPass2026z")
    r = client.get("/api/files", headers=auth_header(data2["access_token"]))
    assert r.status_code == 200


def test_deactivation_revokes_active_token_immediately(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy")
    admin_headers = auth_header(admin["access_token"])

    activate(client, seeded, "agent-dev@test.local", "AgentDevPass26z")
    dev = login(client, "agent-dev@test.local", "AgentDevPass26z")
    dev_headers = auth_header(dev["access_token"])

    r = client.get("/api/admin/users?search=agent-dev", headers=admin_headers)
    dev_id = r.get_json()["utilisateurs"][0]["id"]

    r = client.post(f"/api/admin/users/{dev_id}/deactivate", headers=admin_headers)
    assert r.status_code == 200

    # Correctif : le token de agent-dev, émis AVANT la désactivation,
    # doit être rejeté immédiatement (pas seulement à l'expiration des 8h).
    r = client.get("/api/files", headers=dev_headers)
    assert r.status_code == 401


def test_admin_cannot_force_statut_actif_without_keys(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy")
    headers = auth_header(admin["access_token"])

    r = client.get("/api/admin/users?search=agent-dev", headers=headers)
    dev_id = r.get_json()["utilisateurs"][0]["id"]  # encore EN_ATTENTE, sans clés

    r = client.put(f"/api/admin/users/{dev_id}", headers=headers, json={"statut": "ACTIF"})
    assert r.status_code == 409


def test_delete_pending_account(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy")
    headers = auth_header(admin["access_token"])

    r = client.get("/api/admin/users?search=agent-dev", headers=headers)
    dev_id = r.get_json()["utilisateurs"][0]["id"]

    r = client.delete(f"/api/admin/users/{dev_id}", headers=headers)
    assert r.status_code == 200

    r = client.get("/api/admin/users?search=agent-dev", headers=headers)
    assert r.get_json()["total"] == 0


def test_cannot_delete_already_active_account(client, seeded):
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy")
    headers = auth_header(admin["access_token"])

    activate(client, seeded, "agent-dev@test.local", "AgentDevPass26z")

    r = client.get("/api/admin/users?search=agent-dev", headers=headers)
    dev_id = r.get_json()["utilisateurs"][0]["id"]

    r = client.delete(f"/api/admin/users/{dev_id}", headers=headers)
    assert r.status_code == 409
