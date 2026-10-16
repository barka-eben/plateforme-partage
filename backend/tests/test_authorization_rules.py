"""
Tests des règles d'autorisation : hiérarchie de diffusion, upload
direct, resend-invitation, confirm-download.
"""
import sys
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])
import io
import json

from helpers import activation_payload


def activate(client, seeded, email, password="MotDePasse123xy"):
    token = seeded[email]
    client.post("/api/auth/verify-invitation", json={"email": email, "token": token})
    r = client.post("/api/auth/activate-account", json=activation_payload(email, token, password))
    assert r.status_code == 200, r.get_json()


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_lower_level_cannot_target_higher_level(client, seeded):
    """
    Correctif central : un Agent (ordre 5) ne doit JAMAIS pouvoir
    cibler un Directeur (ordre 2). La version précédente autorisait
    exactement l'inverse de la règle voulue.
    """
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")
    agent = login(client, "agent-rh@test.local", "AgentPass2026xy")

    r = client.post("/api/targets/resolve", headers=auth_header(agent["access_token"]), json={
        "type": "niveau", "target_id": "NIV-002"
    })
    assert r.status_code == 403


def test_higher_level_can_target_lower_level(client, seeded):
    activate(client, seeded, "directeur-rh@test.local", "DirRhPass2026xy")
    directeur = login(client, "directeur-rh@test.local", "DirRhPass2026xy")

    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")  # doit avoir une clé pour être listé

    r = client.post("/api/targets/resolve", headers=auth_header(directeur["access_token"]), json={
        "type": "niveau", "target_id": "NIV-005", "structure_id": "STR-008"
    })
    assert r.status_code == 200
    assert len(r.get_json()["destinataires"]) >= 1


def test_upload_cannot_bypass_target_resolve_authorization(client, seeded):
    """
    Correctif majeur : l'upload direct doit revérifier l'autorisation
    de diffusion, pas seulement /targets/resolve (que le client peut
    simplement ne jamais appeler).
    """
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")
    agent = login(client, "agent-rh@test.local", "AgentPass2026xy")

    activate(client, seeded, "directeur-rh@test.local", "DirRhPass2026xy")
    directeur = login(client, "directeur-rh@test.local", "DirRhPass2026xy")

    # On récupère l'id du directeur via une recherche libre (mode "user"
    # est autorisé sans restriction : seule la voie "niveau" est testée ici).
    r = client.get("/api/users/search?q=directeur-rh", headers=auth_header(agent["access_token"]))
    directeur_id = r.get_json()["utilisateurs"][0]["id"]

    data = {
        "file": (io.BytesIO(b"contenu chiffre bidon"), "x.bin"),
        "hash_sha256": "a" * 64,
        "signature": "sig",
        "nom_chiffre": "x.bin",
        "cle_aes_chiffree_expediteur": "k",
        "diffusions": json.dumps([{"destinataire_id": directeur_id, "cle_aes_chiffree": "k"}]),
        "mode": "niveau",
        "target_niveau_id": "NIV-002",
    }
    r = client.post("/api/files/upload", headers=auth_header(agent["access_token"]),
                     data=data, content_type="multipart/form-data")
    assert r.status_code == 403


def test_upload_mode_user_remains_unrestricted(client, seeded):
    """L'envoi direct à une personne précise reste libre (règle métier)."""
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")
    agent = login(client, "agent-rh@test.local", "AgentPass2026xy")

    activate(client, seeded, "directeur-rh@test.local", "DirRhPass2026xy")

    r = client.get("/api/users/search?q=directeur-rh", headers=auth_header(agent["access_token"]))
    directeur_id = r.get_json()["utilisateurs"][0]["id"]

    data = {
        "file": (io.BytesIO(b"contenu chiffre bidon"), "x.bin"),
        "hash_sha256": "a" * 64,
        "signature": "sig",
        "nom_chiffre": "x.bin",
        "cle_aes_chiffree_expediteur": "k",
        "diffusions": json.dumps([{"destinataire_id": directeur_id, "cle_aes_chiffree": "k"}]),
        "mode": "user",
    }
    r = client.post("/api/files/upload", headers=auth_header(agent["access_token"]),
                     data=data, content_type="multipart/form-data")
    assert r.status_code == 201


def test_resend_invitation_respects_hierarchy(client, seeded):
    """
    Correctif : un « Responsable » (ordre 4) ne doit plus pouvoir
    régénérer le lien d'activation d'un « Directeur » (ordre 2) en
    attente, y compris s'il partage la même structure descendante.
    """
    activate(client, seeded, "admin@plateforme.local", "AdminPass2026xy")
    admin = login(client, "admin@plateforme.local", "AdminPass2026xy")
    admin_headers = auth_header(admin["access_token"])

    r = client.post("/api/admin/users", headers=admin_headers, json={
        "nom": "Superieur", "prenom": "Pending", "email": "sup@test.local",
        "poste_administratif": "Directeur adjoint", "niveau_id": "NIV-002",
        "structure_id": "STR-004",
    })
    sup_id = r.get_json()["user"]["id"]

    activate(client, seeded, "responsable-rh@test.local", "RespPass2026xyz")
    responsable = login(client, "responsable-rh@test.local", "RespPass2026xyz")

    r = client.post(f"/api/admin/users/{sup_id}/resend-invitation",
                     headers=auth_header(responsable["access_token"]))
    assert r.status_code == 403


def test_confirm_download_requires_being_linked_to_the_file(client, seeded):
    """
    Correctif : un utilisateur sans lien avec le fichier ne doit plus
    pouvoir écrire une entrée dans le journal (pollution d'audit).
    """
    activate(client, seeded, "agent-rh@test.local", "AgentPass2026xy")
    agent = login(client, "agent-rh@test.local", "AgentPass2026xy")

    activate(client, seeded, "directeur-rh@test.local", "DirRhPass2026xy")
    directeur = login(client, "directeur-rh@test.local", "DirRhPass2026xy")

    activate(client, seeded, "chef-it@test.local", "ChefItPass2026x")
    chef_it = login(client, "chef-it@test.local", "ChefItPass2026x")

    r = client.get("/api/users/search?q=directeur-rh", headers=auth_header(agent["access_token"]))
    directeur_id = r.get_json()["utilisateurs"][0]["id"]

    data = {
        "file": (io.BytesIO(b"contenu"), "x.bin"),
        "hash_sha256": "a" * 64, "signature": "sig", "nom_chiffre": "x.bin",
        "cle_aes_chiffree_expediteur": "k",
        "diffusions": json.dumps([{"destinataire_id": directeur_id, "cle_aes_chiffree": "k"}]),
        "mode": "user",
    }
    r = client.post("/api/files/upload", headers=auth_header(agent["access_token"]),
                     data=data, content_type="multipart/form-data")
    fichier_id = r.get_json()["fichier_id"]

    # Chef IT n'est ni expéditeur ni destinataire de ce fichier.
    r = client.post(f"/api/files/{fichier_id}/confirm-download",
                     headers=auth_header(chef_it["access_token"]),
                     json={"signature_valide": False})
    assert r.status_code == 403

    # Le destinataire légitime, lui, le peut.
    r = client.post(f"/api/files/{fichier_id}/confirm-download",
                     headers=auth_header(directeur["access_token"]),
                     json={"signature_valide": True})
    assert r.status_code == 200
