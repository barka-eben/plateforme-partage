from app import db


class Historique(db.Model):
    __tablename__ = "historiques"

    id = db.Column(db.String(100), primary_key=True)
    action = db.Column(db.String(150), nullable=False)
    date_action = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    statut_action = db.Column(db.Boolean, nullable=False)

    utilisateur_id = db.Column(
        db.String(100),
        db.ForeignKey("utilisateurs.id"),
        nullable=False
    )

    # Nullable : certaines actions (connexion, échec de connexion sur
    # un email inexistant...) ne concernent aucun fichier précis.
    fichier_id = db.Column(
        db.String(100),
        db.ForeignKey("fichiers.id"),
        nullable=True
    )

    # Cible de l'action, quand l'acteur agit sur UN AUTRE compte
    # (création, modification, activation, désactivation, renvoi
    # d'invitation...). Sans cette colonne, le journal indiquait "X a
    # fait CREATION_COMPTE" sans dire QUEL compte avait été créé —
    # inutilisable pour un vrai audit (correctif traçabilité).
    cible_utilisateur_id = db.Column(
        db.String(100),
        db.ForeignKey("utilisateurs.id"),
        nullable=True
    )

    # Adresse IP de la requête (utile pour détecter une prise de
    # contrôle ou une tentative de force brute distribuée).
    ip_adresse = db.Column(db.String(64), nullable=True)

    # Texte libre optionnel, pour un contexte que les colonnes
    # structurées ne peuvent pas porter (ex : l'email d'un compte
    # EN_ATTENTE supprimé, dont l'id ne peut plus être référencé par
    # cible_utilisateur_id une fois la ligne effacée).
    detail = db.Column(db.String(255), nullable=True)

    utilisateur = db.relationship(
        "User",
        foreign_keys=[utilisateur_id],
        backref="historiques"
    )

    cible_utilisateur = db.relationship(
        "User",
        foreign_keys=[cible_utilisateur_id]
    )

    fichier = db.relationship("Fichier", backref="historiques")
