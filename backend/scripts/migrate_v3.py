# backend/scripts/migrate_v3.py
"""
Migration ponctuelle pour les bases de données créées AVANT les
correctifs de sécurité de cette version (double paire de clés,
révocation de JWT par epoch, journal enrichi, récupération de compte).

`db.create_all()` ne modifie jamais une table déjà existante : ce
script comble l'écart avec de l'ALTER TABLE ciblé, de façon
idempotente (peut être relancé sans risque).

IMPORTANT : les comptes déjà ACTIFS avant cette migration n'ont
qu'UNE SEULE paire de clés RSA (utilisée à la fois pour le chiffrement
et la signature). Cette migration ne peut pas rétroactivement leur
créer une seconde paire (elle ne connaît pas leur mot de passe). Ces
comptes continueront de fonctionner avec leur paire existante tant
qu'ils n'ont pas changé de mot de passe ; un changement de mot de
passe régénère automatiquement deux paires distinctes (cf.
ChangePassword.jsx). Il en va de même pour le code de récupération :
il n'existe pour un compte qu'à partir de son prochain changement de
mot de passe, ou pour tout nouveau compte activé après cette mise à
jour.

Usage :
    python scripts/migrate_v3.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app import create_app, db


def run():
    app = create_app()

    with app.app_context():
        engine_name = db.engine.name
        print(f"Moteur de base de données détecté : {engine_name}")

        if engine_name == "postgresql":
            statements = [
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS cle_publique_signature TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS pbkdf2_iterations INTEGER;",
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS cle_privee_chiffree_recovery TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS sel_recovery TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS recovery_code_hash VARCHAR(64);",
                "ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS jwt_epoch INTEGER NOT NULL DEFAULT 0;",
                "ALTER TABLE historiques ADD COLUMN IF NOT EXISTS cible_utilisateur_id VARCHAR(100);",
                "ALTER TABLE historiques ADD COLUMN IF NOT EXISTS ip_adresse VARCHAR(64);",
                "ALTER TABLE historiques ADD COLUMN IF NOT EXISTS detail VARCHAR(255);",
            ]
        elif engine_name == "sqlite":
            print(
                "SQLite détecté : ALTER TABLE ... ADD COLUMN est supporté pour "
                "des colonnes simples, exécution directe."
            )
            statements = [
                "ALTER TABLE utilisateurs ADD COLUMN cle_publique_signature TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN pbkdf2_iterations INTEGER;",
                "ALTER TABLE utilisateurs ADD COLUMN cle_privee_chiffree_recovery TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN sel_recovery TEXT;",
                "ALTER TABLE utilisateurs ADD COLUMN recovery_code_hash VARCHAR(64);",
                "ALTER TABLE utilisateurs ADD COLUMN jwt_epoch INTEGER NOT NULL DEFAULT 0;",
                "ALTER TABLE historiques ADD COLUMN cible_utilisateur_id VARCHAR(100);",
                "ALTER TABLE historiques ADD COLUMN ip_adresse VARCHAR(64);",
                "ALTER TABLE historiques ADD COLUMN detail VARCHAR(255);",
            ]
        else:
            print(f"Moteur '{engine_name}' non pris en charge par ce script.")
            return

        for stmt in statements:
            try:
                with db.engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()
                print(f"  ✅ {stmt}")
            except Exception as exc:
                print(f"  ⚠️  {stmt}\n     -> {exc}")

        print("\nMigration terminée.")


if __name__ == "__main__":
    run()
