# backend/scripts/init_db.py
"""
Script d'initialisation de la base de données.
Crée les niveaux, les structures, et provisionne les comptes de
démarrage (admin + comptes de démonstration) EN_ATTENTE, comme le
ferait un administrateur via l'interface — c'est-à-dire SANS mot de
passe ni clés, avec un lien d'invitation à activer.

Correctif par rapport à la version précédente : l'admin et les
comptes de démonstration étaient auparavant créés directement ACTIF
avec un mot de passe en dur, mais SANS jamais générer de clés RSA
(elles ne sont générées, par construction, que lors de l'étape
d'activation côté navigateur). Ces comptes ne pouvaient donc jamais
envoyer ni recevoir de fichier chiffré tant qu'ils n'avaient pas
changé leur mot de passe manuellement. Ce script fait maintenant
passer TOUS les comptes par le même parcours d'activation que dans la
vraie vie, et affiche les liens d'invitation en clair dans la console
(jamais via l'API : voir EXPOSE_ACTIVATION_LINK_DEV dans .env.example)
pour pouvoir tester le parcours complet immédiatement.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Niveau, Structure, Statut, Invitation
from app.services.auth_service import generate_invitation_token, invitation_expiration
from app.services.security_service import normalize_email


NIVEAUX_DATA = [
    {"id": "NIV-001", "libelle": "Directeur Général", "ordre": 1},
    {"id": "NIV-002", "libelle": "Directeur", "ordre": 2},
    {"id": "NIV-003", "libelle": "Chef de Service", "ordre": 3},
    {"id": "NIV-004", "libelle": "Responsable", "ordre": 4},
    {"id": "NIV-005", "libelle": "Agent", "ordre": 5},
]

STRUCTURES_DATA = [
    {"id": "STR-001", "nom": "Direction Générale", "parent": None},
    {"id": "STR-002", "nom": "Direction des Ressources Humaines", "parent": "STR-001"},
    {"id": "STR-003", "nom": "Direction des Systèmes d'Information", "parent": "STR-001"},
    {"id": "STR-004", "nom": "Service RH - Opérationnel", "parent": "STR-002"},
    {"id": "STR-005", "nom": "Service RH - Administration", "parent": "STR-002"},
    {"id": "STR-006", "nom": "Service Infrastructure IT", "parent": "STR-003"},
    {"id": "STR-007", "nom": "Service Développement", "parent": "STR-003"},
    {"id": "STR-008", "nom": "Bureau RH - Paie", "parent": "STR-004"},
    {"id": "STR-009", "nom": "Bureau RH - Recrutement", "parent": "STR-004"},
]

# (id, nom, prenom, email, poste, niveau_id, structure_id, est_admin)
COMPTES_A_PROVISIONNER = [
    ("USR-ADMIN-001", "Administrateur", "Système", "admin@plateforme.local",
     "Administrateur Système", "NIV-001", "STR-001", True),
    ("USR-ADMIN-002", "Administrateur", "Système", "admin2@plateforme.local",
     "Administrateur Système", "NIV-001", "STR-001", True),
    ("USR-directeur-rh", "Martin", "Sophie", "directeur-rh@test.local",
     "Directrice des RH", "NIV-002", "STR-002", False),
    ("USR-chef-it", "Dubois", "Thomas", "chef-it@test.local",
     "Chef de Service IT", "NIV-003", "STR-003", False),
    ("USR-responsable-rh", "Petit", "Julie", "responsable-rh@test.local",
     "Responsable RH Opérationnel", "NIV-004", "STR-004", False),
    ("USR-agent-rh", "Lefevre", "Pierre", "agent-rh@test.local",
     "Agent RH", "NIV-005", "STR-008", False),
    ("USR-agent-dev", "Moreau", "Claire", "agent-dev@test.local",
     "Développeuse", "NIV-005", "STR-007", False),
]


def _provisionner(user_id, nom, prenom, email, poste, niveau_id, structure_id, est_admin):
    email = normalize_email(email)
    existing = User.query.filter_by(email=email).first()
    if existing:
        print(f"  ⏭️  Compte déjà existant : {email} (statut={existing.statut.value})")
        return

    user = User(
        id=user_id, nom=nom, prenom=prenom, email=email,
        poste_administratif=poste, est_administrateur_systeme=est_admin,
        statut=Statut.EN_ATTENTE, niveau_id=niveau_id, structure_id=structure_id,
    )
    db.session.add(user)

    token_en_clair, token_hash = generate_invitation_token()
    invitation = Invitation(
        id=f"INV-{user_id}",
        utilisateur_id=user_id,
        token_hash=token_hash,
        date_expiration=invitation_expiration(),
        utilise=False,
    )
    db.session.add(invitation)
    db.session.commit()

    from app.services.email_service import build_activation_link
    link = build_activation_link(email, token_en_clair)

    role = "ADMIN" if est_admin else "compte de démo"
    print(f"  ✅ Provisionné ({role}) : {prenom} {nom} <{email}>")
    print(f"     🔗 Lien d'activation (à usage unique, 24h) : {link}")


def init_database():
    app = create_app()

    with app.app_context():
        print("=" * 70)
        print("🚀 Initialisation de la base de données")
        print("=" * 70)

        print("\n📊 Création des niveaux hiérarchiques...")
        for data in NIVEAUX_DATA:
            if not db.session.get(Niveau, data["id"]):
                db.session.add(Niveau(**data))
                print(f"  ✅ Niveau créé : {data['libelle']} (ordre {data['ordre']})")
        db.session.commit()

        print("\n🏢 Création des structures organisationnelles...")
        for data in STRUCTURES_DATA:
            if not db.session.get(Structure, data["id"]):
                db.session.add(Structure(
                    id=data["id"], nom=data["nom"], structure_parent_id=data["parent"]
                ))
                print(f"  ✅ Structure créée : {data['nom']}")
        db.session.commit()

        print("\n👤 Provisionnement des comptes (admin + démonstration)...")
        print("    Chaque compte doit être ACTIVÉ via son lien ci-dessous")
        print("    (choix du mot de passe + génération des clés dans le navigateur).")
        for compte in COMPTES_A_PROVISIONNER:
            _provisionner(*compte)

        print("\n" + "=" * 70)
        print("✅ Initialisation terminée.")
        print("=" * 70)
        print(f"\n📊 Utilisateurs en base : {User.query.count()}")
        print(f"📊 Niveaux : {Niveau.query.count()} | Structures : {Structure.query.count()}")
        print("\nCopiez-collez un lien d'activation ci-dessus dans le frontend pour")
        print("terminer la création de chaque compte (mot de passe + clés RSA).")


if __name__ == "__main__":
    init_database()
