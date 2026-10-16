from app import db


class Fichier(db.Model):
    __tablename__ = "fichiers"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    nom_chiffre = db.Column(
        db.String(255),
        nullable=False
    )

    hash_sha256 = db.Column(
        db.String(64),
        nullable=False
    )

    signature = db.Column(
        db.Text,
        nullable=False
    )

    date_depot = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    donnee_chiffree = db.Column(
        db.LargeBinary,
        nullable=False
    )

    # Copie de la cle AES du fichier, chiffree avec la cle publique
    # de l'EXPEDITEUR lui-meme (RSA-OAEP), pour qu'il puisse rouvrir
    # ses propres envois plus tard sans dependre de la cle chiffree
    # d'un destinataire (qui n'est pas dechiffrable par lui).
    cle_aes_chiffree_expediteur = db.Column(
        db.Text,
        nullable=True
    )

    expediteur_id = db.Column(
        db.String(100),
        db.ForeignKey("utilisateurs.id"),
        nullable=False
    )

    expediteur = db.relationship(
        "User",
        backref="fichiers_envoyes"
    )