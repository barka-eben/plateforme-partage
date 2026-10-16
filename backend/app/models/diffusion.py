from app import db


class Diffusion(db.Model):
    __tablename__ = "diffusions"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    cle_aes_chiffree = db.Column(
        db.Text,
        nullable=False
    )

    statut_lecture = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    date_acces = db.Column(
        db.DateTime,
        nullable=True
    )

    fichier_id = db.Column(
        db.String(100),
        db.ForeignKey("fichiers.id"),
        nullable=False
    )

    destinataire_id = db.Column(
        db.String(100),
        db.ForeignKey("utilisateurs.id"),
        nullable=False
    )

    fichier = db.relationship(
        "Fichier",
        backref="diffusions"
    )

    destinataire = db.relationship(
        "User",
        backref="diffusions_recues"
    )