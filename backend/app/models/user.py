from enum import Enum

from app import db


class Statut(Enum):
    # Compte cree par un admin/habilite, en attente que l'utilisateur
    # ouvre son lien d'invitation et choisisse son mot de passe definitif.
    EN_ATTENTE = "EN_ATTENTE"
    ACTIF = "ACTIF"
    # Compte desactive (soft delete) par un administrateur.
    INACTIF = "INACTIF"


class User(db.Model):
    __tablename__ = "utilisateurs"

    id = db.Column(db.String(100), primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    poste_administratif = db.Column(db.String(150), nullable=False)
    est_administrateur_systeme = db.Column(db.Boolean, default=False, nullable=False)

    # Clé publique RSA-OAEP (chiffrement de la clé AES des fichiers).
    cle_publique = db.Column(db.Text, nullable=True)

    # Clé publique RSA-PSS (vérification de signature). Séparée de la
    # clé OAEP : une même paire RSA ne doit jamais servir à la fois au
    # chiffrement et à la signature (correctif sécurité : les deux
    # étaient auparavant la même paire).
    cle_publique_signature = db.Column(db.Text, nullable=True)

    mot_de_passe_hash = db.Column(db.String(255), nullable=True)

    # Blob unique = { oaepPriv, pssPriv } (JSON base64), chiffré en
    # AES-256-GCM avec la clé dérivée du mot de passe (PBKDF2).
    cle_privee_chiffree = db.Column(db.Text, nullable=True)

    sel_derivation_cle = db.Column(db.Text, nullable=True)

    # Nombre d'itérations PBKDF2 utilisées pour CE sel. Stocké pour
    # pouvoir faire évoluer la recommandation plus tard (OWASP 2023 :
    # 600 000 itérations pour PBKDF2-HMAC-SHA256) sans casser le
    # déchiffrement des comptes déjà activés avec l'ancienne valeur.
    pbkdf2_iterations = db.Column(db.Integer, nullable=True)

    # ------------------------------------------------------------
    # Récupération de compte (mot de passe oublié)
    # ------------------------------------------------------------
    # Même blob de clés privées, mais chiffré avec une clé dérivée
    # d'un CODE DE RÉCUPÉRATION à haute entropie (généré côté
    # navigateur, affiché une seule fois à l'activation). Le code
    # n'est jamais stocké en clair : seule son empreinte SHA-256
    # (recovery_code_hash) est conservée, pour vérifier sa validité
    # avant de renvoyer le blob chiffré au navigateur.
    cle_privee_chiffree_recovery = db.Column(db.Text, nullable=True)
    sel_recovery = db.Column(db.Text, nullable=True)
    recovery_code_hash = db.Column(db.String(64), nullable=True)

    # Incrémenté à chaque désactivation de compte ou changement de
    # mot de passe : la valeur est embarquée dans le JWT au login, et
    # comparée à la valeur courante en base à chaque requête protégée
    # (cf. jwt_epoch_loader dans app/__init__.py). Un token émis avant
    # l'incrément devient ainsi invalide immédiatement, sans attendre
    # son expiration naturelle.
    jwt_epoch = db.Column(db.Integer, default=0, nullable=False)

    statut = db.Column(db.Enum(Statut), default=Statut.EN_ATTENTE, nullable=False)

    niveau_id = db.Column(db.String(100), db.ForeignKey("niveaux.id"), nullable=False)
    structure_id = db.Column(db.String(100), db.ForeignKey("structures.id"), nullable=False)

    niveau = db.relationship("Niveau", backref="utilisateurs")
    structure = db.relationship("Structure", backref="utilisateurs")
