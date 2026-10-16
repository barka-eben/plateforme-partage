from app import db


class Structure(db.Model):
    __tablename__ = "structures"

    id = db.Column(
        db.String(100),
        primary_key=True
    )

    nom = db.Column(
        db.String(150),
        nullable=False
    )

    structure_parent_id = db.Column(
        db.String(100),
        db.ForeignKey("structures.id"),
        nullable=True
    )

    structure_parent = db.relationship(
        "Structure",
        remote_side=[id],
        backref="sous_structures"
    )