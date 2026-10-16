# backend/scripts/migrate_v2.py
"""
Migration ponctuelle pour les bases de données créées AVANT les
correctifs/ajouts apportés aux modèles (Historique.fichier_id
nullable, Fichier.cle_aes_chiffree_expediteur, Statut.EN_ATTENTE).

`db.create_all()` ne modifie jamais une table déjà existante : ce
script comble l'écart avec de l'ALTER TABLE ciblé, de façon
idempotente (peut être relancé sans risque).

Usage :
    python scripts/migrate_v2.py
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

        statements = []

        if engine_name == "postgresql":
            statements = [
                # 1. fichier_id devient nullable (connexions, créations
                #    de compte, etc. ne concernent aucun fichier)
                "ALTER TABLE historiques ALTER COLUMN fichier_id DROP NOT NULL;",

                # 2. nouvelle colonne : copie de la clé AES pour l'expéditeur
                'ALTER TABLE fichiers ADD COLUMN IF NOT EXISTS '
                'cle_aes_chiffree_expediteur TEXT;',

                # 3. nouvelle valeur d'enum : statut "en attente d'activation"
                "ALTER TYPE statut ADD VALUE IF NOT EXISTS 'EN_ATTENTE';",
            ]
        elif engine_name == "sqlite":
            # SQLite : ALTER COLUMN n'existe pas, et les enums sont
            # stockés comme du texte libre (pas de type contraint), donc
            # rien à migrer pour l'enum. Pour fichier_id/nouvelle colonne,
            # le plus simple en dev est de supprimer le fichier .db et de
            # relancer l'application (db.create_all() recréera tout).
            print(
                "SQLite détecté : aucune migration automatique nécessaire "
                "pour l'enum. Si la base existait déjà AVANT les derniers "
                "changements de modèles, supprimez le fichier .sqlite3 et "
                "relancez l'application pour que les tables soient "
                "recréées avec le bon schéma."
            )
        else:
            print(f"Moteur '{engine_name}' non pris en charge par ce script.")
            return

        for stmt in statements:
            try:
                # ALTER TYPE ... ADD VALUE ne peut pas s'exécuter dans une
                # transaction avec d'autres commandes sur Postgres < 12 ;
                # on committe donc après CHAQUE instruction, séparément.
                with db.engine.connect() as conn:
                    conn.execute(text(stmt))
                    conn.commit()
                print(f"  ✅ {stmt}")
            except Exception as exc:
                print(f"  ⚠️  {stmt}\n     -> {exc}")

        print("\nMigration terminée.")


if __name__ == "__main__":
    run()
