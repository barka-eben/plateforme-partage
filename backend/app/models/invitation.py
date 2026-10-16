from app import db


class Invitation(db.Model):
    """
    Represente un lien d'invitation a usage unique envoye a un
    utilisateur nouvellement provisionne.

    On ne stocke jamais le token en clair : uniquement son hash
    (sha256), pour qu'une fuite de la base ne permette pas de
    rejouer une invitation (meme logique qu'un mot de passe).
    """

    __tablename__ = "invitations"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    utilisateur_id = db.Column(
        db.String(100),
        db.ForeignKey("utilisateurs.id"),
        nullable=False
    )

    token_hash = db.Column(
        db.String(255),
        nullable=False
    )

    date_creation = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False
    )

    date_expiration = db.Column(
        db.DateTime,
        nullable=False
    )

    utilise = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    utilisateur = db.relationship(
        "User",
        backref="invitations"
    )
