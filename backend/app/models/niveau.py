from app import db


class Niveau(db.Model):
    __tablename__ = "niveaux"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    libelle = db.Column(
        db.String(100),
        nullable=False
    )

    ordre = db.Column(
        db.Integer,
        nullable=False
    )