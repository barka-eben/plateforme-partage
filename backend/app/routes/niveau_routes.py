# backend/app/routes/niveau_routes.py
"""
Gestion des niveaux hierarchiques configurables.

Le cahier des charges (section 2.1) precise que les niveaux ne sont
PAS une liste figee (agent/responsable/admin) mais sont crees et
modifies par l'administrateur systeme : un libelle + un ordre
numerique (le plus petit = le plus eleve). Ces routes manquaient
entierement dans la version initiale du backend.
"""

import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import User, Niveau

niveau_bp = Blueprint(
    "niveaux",
    __name__,
    url_prefix="/api/admin/niveaux"
)


def _current_user():
    return db.session.get(User, get_jwt_identity())


# ================================================================
# GET /api/admin/niveaux - lecture ouverte a tout utilisateur connecte
# (necessaire pour peupler les formulaires : creation de compte,
# ciblage de diffusion, etc.)
# ================================================================

@niveau_bp.route("", methods=["GET"])
@jwt_required()
def list_niveaux():
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    niveaux = Niveau.query.order_by(Niveau.ordre.asc()).all()

    return jsonify({
        "niveaux": [
            {"id": n.id, "libelle": n.libelle, "ordre": n.ordre}
            for n in niveaux
        ]
    }), 200


# ================================================================
# POST /api/admin/niveaux - creation, reservee a l'admin systeme
# ================================================================

@niveau_bp.route("", methods=["POST"])
@jwt_required()
def create_niveau():
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut créer un niveau"
        }), 403

    data = request.get_json() or {}
    libelle = data.get("libelle")
    ordre = data.get("ordre")

    if not libelle or ordre is None:
        return jsonify({"message": "libelle et ordre sont requis"}), 400

    try:
        ordre = int(ordre)
    except (TypeError, ValueError):
        return jsonify({"message": "ordre doit être un entier"}), 400

    if Niveau.query.filter_by(ordre=ordre).first():
        return jsonify({
            "message": f"Un niveau avec l'ordre {ordre} existe déjà"
        }), 409

    niveau = Niveau(
        id=f"NIV-{uuid.uuid4()}",
        libelle=libelle,
        ordre=ordre
    )

    db.session.add(niveau)
    db.session.commit()

    return jsonify({
        "message": "Niveau créé avec succès",
        "niveau": {"id": niveau.id, "libelle": niveau.libelle, "ordre": niveau.ordre}
    }), 201


# ================================================================
# PUT /api/admin/niveaux/<id> - modification, admin systeme uniquement
# ================================================================

@niveau_bp.route("/<niveau_id>", methods=["PUT"])
@jwt_required()
def update_niveau(niveau_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut modifier un niveau"
        }), 403

    niveau = db.session.get(Niveau, niveau_id)
    if not niveau:
        return jsonify({"message": "Niveau introuvable"}), 404

    data = request.get_json() or {}

    if "libelle" in data:
        niveau.libelle = data["libelle"]

    if "ordre" in data:
        try:
            nouvel_ordre = int(data["ordre"])
        except (TypeError, ValueError):
            return jsonify({"message": "ordre doit être un entier"}), 400

        conflit = Niveau.query.filter(
            Niveau.ordre == nouvel_ordre,
            Niveau.id != niveau_id
        ).first()
        if conflit:
            return jsonify({
                "message": f"Un niveau avec l'ordre {nouvel_ordre} existe déjà"
            }), 409

        niveau.ordre = nouvel_ordre

    db.session.commit()

    return jsonify({
        "message": "Niveau modifié avec succès",
        "niveau": {"id": niveau.id, "libelle": niveau.libelle, "ordre": niveau.ordre}
    }), 200


# ================================================================
# DELETE /api/admin/niveaux/<id> - suppression, admin systeme uniquement
# ================================================================

@niveau_bp.route("/<niveau_id>", methods=["DELETE"])
@jwt_required()
def delete_niveau(niveau_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut supprimer un niveau"
        }), 403

    niveau = db.session.get(Niveau, niveau_id)
    if not niveau:
        return jsonify({"message": "Niveau introuvable"}), 404

    utilisateurs_lies = User.query.filter_by(niveau_id=niveau_id).count()
    if utilisateurs_lies > 0:
        return jsonify({
            "message": f"Impossible de supprimer : {utilisateurs_lies} utilisateur(s) "
                       "sont encore rattachés à ce niveau"
        }), 409

    db.session.delete(niveau)
    db.session.commit()

    return jsonify({"message": "Niveau supprimé avec succès"}), 200
