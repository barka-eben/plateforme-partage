# Scripts

- `init_db.py` — crée les tables, les niveaux, les structures, et
  provisionne l'admin + des comptes de démonstration (EN_ATTENTE,
  avec lien d'activation affiché en console).
- `migrate_v3.py` — ajoute les colonnes introduites par les correctifs
  de sécurité à une base déjà existante (PostgreSQL ou SQLite).
- `migrate_v2.py` — migration historique conservée pour référence.
- `clean_db.py` — vide les tables (développement uniquement).
- `reset_passwords.py` — **ne fait plus rien** : explique pourquoi
  l'ancien comportement était dangereux et pointe vers le vrai
  parcours de récupération (page /mot-de-passe-oublie).

Les anciens `test_routes.py` et `test_authorization.py` (scripts sans
assertions, nécessitant `requests`) ont été remplacés par une vraie
suite de tests : voir `backend/tests/` (`pytest`).
