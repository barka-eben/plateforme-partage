# Plateforme de partage sécurisé — Backend Flask + Frontend React

Application de diffusion de documents chiffrés de bout en bout entre agents
d'une administration, organisée par niveaux hiérarchiques et structures.

Ce paquet est une **version corrigée** d'un audit de sécurité complet, portant
en particulier sur la création et l'activation de compte. Cette section
documente **ce qui a changé et pourquoi** ; voir aussi les commentaires dans
le code (chaque correctif y est expliqué à l'endroit précis où il s'applique).

---

## 1. Démarrage rapide

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Éditez .env : DATABASE_URL, et générez un vrai secret avec :
python -c "import secrets; print(secrets.token_hex(32))"
# -> collez le résultat dans JWT_SECRET

python scripts/init_db.py       # crée niveaux / structures / comptes, affiche les liens d'activation
python run.py                   # démarre sur http://127.0.0.1:5000
```

Chaque compte provisionné par `init_db.py` (y compris l'administrateur) est
créé **EN_ATTENTE**, avec un lien d'activation affiché dans la console.
Copiez ce lien dans le frontend pour terminer sa création (choix du mot de
passe + génération des clés, exactement comme le ferait un vrai utilisateur).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_URL doit pointer vers le backend
npm run dev              # http://localhost:5173
```

### Tests backend (pytest)

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v
```

20 tests couvrent le cycle de vie d'un compte, les règles hiérarchiques, la
récupération de mot de passe et la limitation de débit. Ils exercent l'API
Flask réelle (via `test_client`), avec des blobs cryptographiques factices
mais de la bonne taille — ils valident donc le **comportement de l'API**, pas
la correction cryptographique du protocole (couverte manuellement, voir
section 6).

---

## 2. Ce qui a changé — création et activation de compte

C'était la partie la plus fragile de l'audit initial. Par ordre d'impact :

### Bloquant : l'envoi de fichiers ne fonctionnait pour personne
`/auth/login` ne renvoyait pas la clé publique de l'utilisateur, alors que le
frontend en avait besoin pour chiffrer quoi que ce soit. **Corrigé** : le
login (et `/auth/me`) renvoient désormais `cle_publique` (RSA-OAEP) et
`cle_publique_signature` (RSA-PSS).

### Le lien d'activation ne fuit plus par défaut
`EXPOSE_ACTIVATION_LINK_DEV` (renommé, ancien nom `EXPOSE_ACTIVATION_LINK`)
est maintenant **fermé par défaut** et indépendant de `FLASK_DEBUG`. Un
manager qui crée un compte ne reçoit plus le lien d'activation de ce compte
dans la réponse API : sans SMTP configuré, le lien s'affiche uniquement dans
les **logs serveur** (jamais transmis au client HTTP).

### Deux paires de clés RSA, plus une seule
Chiffrement (RSA-OAEP) et signature (RSA-PSS) utilisent désormais deux paires
de clés distinctes, générées ensemble à l'activation et regroupées dans un
même blob chiffré (voir `cryptoService.js`, `encryptPrivateBundle`).

### Mot de passe trop long : géré proprement
bcrypt lève une exception au-delà de 72 octets. Le serveur refuse maintenant
proprement (`400`/`401`) au lieu de planter (`500`), à l'activation comme au
login.

### Récupération de compte (nouveau)
Il n'existait auparavant **aucun** moyen de récupérer un compte dont le mot
de passe était perdu, sans casser irrémédiablement l'accès aux fichiers déjà
reçus. Un **code de récupération** à haute entropie (~130 bits) est
maintenant généré côté navigateur à l'activation, affiché **une seule fois**,
et sert à déchiffrer une seconde copie du blob de clés privées en cas
d'oubli du mot de passe (page `/mot-de-passe-oublie`). Le serveur ne voit
jamais ce code en clair (seule son empreinte SHA-256 est stockée) et ne peut
donc pas déchiffrer les clés privées lui-même.

**Limite assumée** : si le mot de passe *et* le code de récupération sont
tous les deux perdus, il n'existe **aucun** moyen de récupérer les fichiers
déjà chiffrés pour ce compte. C'est la garantie du chiffrement de bout en
bout, pas un oubli — voir `backend/scripts/reset_passwords.py` (l'ancien
script, dangereux, a été retiré et remplacé par une note explicative).

### Révocation immédiate des sessions
Un JWT émis avant une désactivation de compte ou un changement de mot de
passe restait valide jusqu'à 8h. Chaque utilisateur porte maintenant un
compteur `jwt_epoch`, embarqué dans le token et revérifié à chaque requête :
désactiver un compte ou changer son mot de passe invalide **immédiatement**
tous les tokens déjà émis.

### Règles d'autorisation renforcées
- **Règle hiérarchique de diffusion inversée** : elle interdisait de cibler
  les niveaux inférieurs et autorisait les niveaux supérieurs — l'exact
  opposé de la règle voulue. Corrigée dans `target_routes.py`.
- **L'upload direct ne contourne plus les règles** : `/files/upload`
  revérifie désormais lui-même l'autorisation de diffusion (mode
  `user`/`niveau`/`all`), pas seulement `/targets/resolve`.
- **`resend-invitation` applique enfin la règle de niveau** (un manager ne
  peut plus régénérer le lien d'un compte hiérarchiquement supérieur).
- **`confirm-download` exige un lien réel avec le fichier** (expéditeur ou
  destinataire), pour ne plus polluer le journal d'audit.
- **Un admin ne peut plus forcer `statut=ACTIF`** sur un compte sans clés
  publiques (il doit passer par l'invitation).
- **Emails normalisés** (insensibles à la casse) partout où c'est pertinent.

### Autres correctifs de cette section
- Limitation de débit (`flask-limiter`) sur login, activation, vérification
  d'invitation et récupération de compte.
- Messages de login partiellement uniformisés : pour un compte `ACTIF` ou
  `INACTIF`, le mot de passe est vérifié **avant** de révéler le statut (un
  tiers sans mot de passe ne peut plus confirmer qu'un compte désactivé
  existe). Un compte `EN_ATTENTE` n'a structurellement pas de mot de passe :
  cette énumération résiduelle est documentée, pas cachée.
- Validation des blobs cryptographiques envoyés à l'activation (taille et
  encodage plausibles), pour ne plus pouvoir « briquer » un compte avec une
  clé publique invalide.
- Suppression possible d'un compte `EN_ATTENTE` (erreur de saisie d'email) ;
  email éditable dans le formulaire de modification.
- Journal d'audit enrichi : cible de l'action, adresse IP, champ « detail »
  libre (ex : email d'un compte `EN_ATTENTE` supprimé).
- La création de compte est désormais accessible aux managers habilités
  (pas seulement à l'administrateur système) dans l'interface — le backend
  l'autorisait déjà, l'UI le bloquait.
- `autoComplete` correct sur tous les champs de mot de passe (les
  gestionnaires de mots de passe proposent enfin d'enregistrer un mot de
  passe qui, rappelons-le, n'est récupérable par personne s'il est perdu).
- `run.py` : `debug=False` et hôte `127.0.0.1` par défaut (plus d'exposition
  du débogueur Werkzeug sur le réseau).
- Gestion globale du `401` côté frontend (session expirée/révoquée
  proprement signalée, au lieu d'une UI silencieusement cassée).

---

## 3. Ce qui n'a **pas** été refait entièrement

Par souci de rester dans un périmètre raisonnable, certains points de
l'audit sont documentés mais pas ré-architecturés :

- **PBKDF2** est passé à 600 000 itérations (recommandation OWASP pour
  SHA-256), mais reste une fonction non memory-hard. Un passage à Argon2id
  serait préférable à long terme mais change le format de stockage.
- Les **comptes déjà actifs avant cette mise à jour** (s'il en existe) n'ont
  qu'une seule paire de clés RSA et pas de code de récupération tant qu'ils
  n'ont pas changé de mot de passe (voir `scripts/migrate_v3.py`).
- Le stockage des fichiers reste en base de données (`LargeBinary`), pas sur
  un stockage objet dédié — acceptable pour le volume visé, à revoir sinon.
- Pas de MFA (recommandé au minimum pour les comptes administrateur).

---

## 4. Variables d'environnement clés (`backend/.env`)

Voir `.env.example` pour la liste complète et commentée. Les plus
sensibles :

| Variable | Rôle |
|---|---|
| `JWT_SECRET` | Signature des JWT. Générez une vraie valeur aléatoire. |
| `EXPOSE_ACTIVATION_LINK_DEV` | **`0` partout sauf poste de dev strictement local.** |
| `RATELIMIT_ENABLED` | Désactivez uniquement pour des tests automatisés. |
| `MAX_CONTENT_LENGTH_MB` | Taille max d'un upload (défaut 60 Mo). |

---

## 5. Migration d'une base existante

Si vous avez déjà une base créée avec une version antérieure à ces
correctifs :

```bash
python scripts/migrate_v3.py
```

Ce script ajoute les colonnes manquantes (deux clés publiques, epoch JWT,
champs de récupération, journal enrichi) sans toucher aux données
existantes. Voir le docstring du script pour les limites (comptes déjà
actifs sans seconde paire de clés).

---

## 6. Comment ceci a été vérifié

- **pytest** (`backend/tests/`, 20 tests) : cycle de vie de compte, règles
  d'autorisation, récupération, contre l'API Flask réelle.
- **Bout en bout manuel** : le vrai code `cryptoService.js` /
  `fileTransfer.js` / `api.js` exécuté sous Node.js contre le vrai backend
  Flask (SQLite), pour valider le protocole cryptographique complet
  (génération de clés, chiffrement, signature, vérification avant
  déchiffrement, récupération de compte) — ce que pytest seul ne peut pas
  couvrir puisque la cryptographie vit côté navigateur.
- **`npm run build`** : la compilation de production du frontend passe sans
  erreur.

---

## 7. Structure du projet

```
backend/
  app/
    models/       # User, Niveau, Structure, Fichier, Diffusion, Historique, Invitation
    routes/       # auth, admin, files, targets, history, niveaux, structures, directory
    services/     # auth, email, history, authorization, security (nouveau)
  scripts/        # init_db, migrate_v3, clean_db, reset_passwords (désactivé, voir plus haut)
  tests/          # pytest
frontend/
  src/
    crypto/       # cryptoService.js — toute la cryptographie, exécutée dans le navigateur
    services/     # api.js, fileTransfer.js
    context/      # AuthContext.jsx
    pages/        # Login, ActivateAccount, ForgotPassword (nouveau), ChangePassword, ...
    components/   # layout, files, admin, common
```
