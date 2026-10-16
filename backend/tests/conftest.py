"""
Configuration pytest partagée.

Chaque test reçoit une base SQLite fraîche (fichier temporaire), avec
les niveaux/structures/comptes de démonstration déjà provisionnés
EN_ATTENTE (mêmes données que scripts/init_db.py), pour ne pas
dupliquer cette logique.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
    os.environ["RATELIMIT_ENABLED"] = "0"
    os.environ.pop("EXPOSE_ACTIVATION_LINK_DEV", None)

    # Ré-importer proprement à chaque test (évite les blueprints déjà
    # enregistrés sur un module Flask mis en cache entre les tests).
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from app import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        import scripts.init_db as init_db
        init_db.init_database.__wrapped__ = None  # no-op, garde la fonction telle quelle

    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded(app, client):
    """Provisionne niveaux/structures/comptes de démo, retourne les liens d'invitation en clair."""
    import scripts.init_db as init_db

    with app.app_context():
        init_db.init_database()

    # Récupère les tokens d'invitation en clair en les régénérant nous
    # même ici (init_database() ne les renvoie pas, il les imprime) :
    # plus simple et plus robuste pour les tests que de parser stdout.
    from app import db
    from app.models import User, Invitation
    from app.services.auth_service import generate_invitation_token, invitation_expiration

    links = {}
    with app.app_context():
        users = User.query.all()
        for u in users:
            Invitation.query.filter_by(utilisateur_id=u.id).delete()
            token_en_clair, token_hash = generate_invitation_token()
            inv = Invitation(
                id=f"INV-TEST-{u.id}",
                utilisateur_id=u.id,
                token_hash=token_hash,
                date_expiration=invitation_expiration(),
                utilise=False,
            )
            db.session.add(inv)
            links[u.email] = token_en_clair
        db.session.commit()

    return links
