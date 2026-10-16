# backend/app/routes/structure_routes.py
"""
Gestion de l'arbre organisationnel (Structure).

Le cahier des charges (section 2.2) decrit un arbre de structures
(direction -> service -> bureau) sur autant de niveaux que necessaire.
Ces routes manquaient entierement dans la version initiale du
backend : sans elles, impossible pour le frontend d'afficher
l'organigramme ou de le faire administrer.
"""

import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import User, Structure
from app.services.authorization_service import (
    get_descendant_structure_ids,
    structure_has_users_or_children
)

structure_bp = Blueprint(
    "structures",
    __name__,
    url_prefix="/api/admin/structures"
)


def _current_user():
    return db.session.get(User, get_jwt_identity())


def _build_tree(structures):
    """Transforme une liste plate de structures en arbre imbriqué."""
    by_id = {s.id: {
        "id": s.id,
        "nom": s.nom,
        "structure_parent_id": s.structure_parent_id,
        "enfants": []
    } for s in structures}

    racine = []

    for s in structures:
        node = by_id[s.id]
        if s.structure_parent_id and s.structure_parent_id in by_id:
            by_id[s.structure_parent_id]["enfants"].append(node)
        else:
            racine.append(node)

    return racine


# ================================================================
# GET /api/admin/structures - liste plate (lecture ouverte)
# ================================================================

@structure_bp.route("", methods=["GET"])
@jwt_required()
def list_structures():
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    structures = Structure.query.order_by(Structure.nom.asc()).all()

    return jsonify({
        "structures": [
            {
                "id": s.id,
                "nom": s.nom,
                "structure_parent_id": s.structure_parent_id
            }
            for s in structures
        ]
    }), 200


# ================================================================
# GET /api/admin/structures/tree - arbre complet (lecture ouverte)
# ================================================================

@structure_bp.route("/tree", methods=["GET"])
@jwt_required()
def get_structure_tree():
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    structures = Structure.query.order_by(Structure.nom.asc()).all()

    return jsonify({"arbre": _build_tree(structures)}), 200


# ================================================================
# POST /api/admin/structures - creation
# Autorisee a l'admin systeme, ou a un utilisateur habilite pour
# creer une sous-structure DANS une structure qu'il gere deja
# (sa structure ou une structure descendante).
# ================================================================

@structure_bp.route("", methods=["POST"])
@jwt_required()
def create_structure():
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    data = request.get_json() or {}
    nom = data.get("nom")
    structure_parent_id = data.get("structure_parent_id")

    if not nom:
        return jsonify({"message": "nom est requis"}), 400

    if structure_parent_id:
        parent = db.session.get(Structure, structure_parent_id)
        if not parent:
            return jsonify({"message": "Structure parente introuvable"}), 404

    if not user.est_administrateur_systeme:
        if not structure_parent_id:
            return jsonify({
                "message": "Vous devez rattacher la nouvelle unité à une "
                           "structure existante que vous gérez"
            }), 403

        gerables = get_descendant_structure_ids(user.structure_id)
        if structure_parent_id not in gerables:
            return jsonify({
                "message": "Vous ne pouvez créer une unité que sous votre "
                           "propre structure ou une structure descendante"
            }), 403

    structure = Structure(
        id=f"STR-{uuid.uuid4()}",
        nom=nom,
        structure_parent_id=structure_parent_id
    )

    db.session.add(structure)
    db.session.commit()

    return jsonify({
        "message": "Structure créée avec succès",
        "structure": {
            "id": structure.id,
            "nom": structure.nom,
            "structure_parent_id": structure.structure_parent_id
        }
    }), 201


# ================================================================
# PUT /api/admin/structures/<id> - renommer / redeplacer
# ================================================================

@structure_bp.route("/<structure_id>", methods=["PUT"])
@jwt_required()
def update_structure(structure_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    structure = db.session.get(Structure, structure_id)
    if not structure:
        return jsonify({"message": "Structure introuvable"}), 404

    if not user.est_administrateur_systeme:
        gerables = get_descendant_structure_ids(user.structure_id)
        if structure_id not in gerables:
            return jsonify({
                "message": "Vous ne pouvez modifier que votre structure ou "
                           "une structure descendante"
            }), 403

    data = request.get_json() or {}

    if "nom" in data:
        structure.nom = data["nom"]

    if "structure_parent_id" in data:
        nouveau_parent_id = data["structure_parent_id"]

        if nouveau_parent_id == structure_id:
            return jsonify({
                "message": "Une structure ne peut pas être son propre parent"
            }), 400

        if nouveau_parent_id:
            nouveau_parent = db.session.get(Structure, nouveau_parent_id)
            if not nouveau_parent:
                return jsonify({"message": "Nouvelle structure parente introuvable"}), 404

            # Empecher de creer un cycle (deplacer un noeud sous l'un
            # de ses propres descendants).
            descendants = get_descendant_structure_ids(structure_id)
            if nouveau_parent_id in descendants:
                return jsonify({
                    "message": "Déplacement invalide : créerait une boucle "
                               "dans l'arbre organisationnel"
                }), 400

        structure.structure_parent_id = nouveau_parent_id

    db.session.commit()

    return jsonify({
        "message": "Structure modifiée avec succès",
        "structure": {
            "id": structure.id,
            "nom": structure.nom,
            "structure_parent_id": structure.structure_parent_id
        }
    }), 200


# ================================================================
# DELETE /api/admin/structures/<id>
# ================================================================

@structure_bp.route("/<structure_id>", methods=["DELETE"])
@jwt_required()
def delete_structure(structure_id):
    user = _current_user()
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut supprimer une structure"
        }), 403

    structure = db.session.get(Structure, structure_id)
    if not structure:
        return jsonify({"message": "Structure introuvable"}), 404

    if structure_has_users_or_children(structure_id):
        return jsonify({
            "message": "Impossible de supprimer : cette structure contient "
                       "encore des utilisateurs ou des sous-structures"
        }), 409

    db.session.delete(structure)
    db.session.commit()

    return jsonify({"message": "Structure supprimée avec succès"}), 200
