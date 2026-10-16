# backend/app/routes/directory_routes.py
"""
Annuaire minimal des utilisateurs actifs.

Manquait entierement dans la version initiale du backend : la route
POST /api/targets/resolve (type="user") suppose deja connu l'id du
destinataire, mais rien ne permettait a un utilisateur de RECHERCHER
un collegue par nom pour l'envoi d'un fichier a une personne precise
(regle metier : "l'envoi a une personne precise est libre", donc pas
de restriction hierarchique ici - juste une recherche par texte).

On ne renvoie que le strict necessaire pour chiffrer/afficher : pas
de hash de mot de passe, pas de cle privee, pas de statut sensible.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app import db
from app.models import User, Statut

directory_bp = Blueprint(
    "directory",
    __name__,
    url_prefix="/api/users"
)


@directory_bp.route("/search", methods=["GET"])
@jwt_required()
def search_users():
    current_user_id = get_jwt_identity()

    q = (request.args.get("q") or "").strip()
    limit = min(request.args.get("limit", 10, type=int), 25)

    if len(q) < 2:
        return jsonify({"utilisateurs": []}), 200

    users = User.query.filter(
        User.statut == Statut.ACTIF,
        User.id != current_user_id,
        User.cle_publique.isnot(None),  # ne peut recevoir un fichier chiffré sans clé publique
        or_(
            User.nom.ilike(f"%{q}%"),
            User.prenom.ilike(f"%{q}%"),
            User.email.ilike(f"%{q}%")
        )
    ).limit(limit).all()

    return jsonify({
        "utilisateurs": [
            {
                "id": u.id,
                "nom": u.nom,
                "prenom": u.prenom,
                "email": u.email,
                "poste_administratif": u.poste_administratif,
                "cle_publique": u.cle_publique,
                "cle_publique_signature": u.cle_publique_signature
            }
            for u in users
        ]
    }), 200
