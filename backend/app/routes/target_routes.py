# backend/app/routes/target_routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import User, Niveau, Structure, Statut
from app.services.authorization_service import get_descendant_structure_ids


target_bp = Blueprint(
    "targets",
    __name__,
    url_prefix="/api/targets"
)


def _serialize_recipient(u):
    return {
        "id": u.id,
        "nom": u.nom,
        "prenom": u.prenom,
        "email": u.email,
        "cle_publique": u.cle_publique,
        "cle_publique_signature": u.cle_publique_signature
    }


@target_bp.route("/resolve", methods=["POST"])
@jwt_required()
def resolve_target():
    """
    Résout une cible en liste de destinataires.

    Types de cibles :
    - "user" : un utilisateur spécifique
    - "niveau" : tous les utilisateurs d'un niveau
    - "all" : tous les utilisateurs (admin ou niveau le plus élevé)
    """

    current_user_id = get_jwt_identity()
    current_user = db.session.get(User, current_user_id)

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"message": "Données manquantes"}), 400

    target_type = data.get("type")
    target_id = data.get("target_id")
    structure_id = data.get("structure_id")

    if not target_type:
        return jsonify({"message": "Le type de cible est requis"}), 400

    # ==========================================================
    # CAS 1 : TARGET "USER" - Une personne précise
    # ==========================================================
    # Règle métier explicite : l'envoi à une personne précise est
    # libre, sans restriction hiérarchique (contrairement aux modes
    # "niveau" et "all").

    if target_type == "user":
        if not target_id:
            return jsonify({"message": "target_id requis pour le type 'user'"}), 400

        user = db.session.get(User, target_id)
        if not user:
            return jsonify({"message": "Utilisateur introuvable"}), 404

        if user.statut != Statut.ACTIF:
            return jsonify({"message": "L'utilisateur cible est inactif"}), 403

        if not user.cle_publique:
            return jsonify({
                "message": "Cet utilisateur n'a pas encore activé son compte "
                           "(aucune clé de chiffrement disponible) : il ne "
                           "peut pas encore recevoir de fichier"
            }), 409

        return jsonify({"destinataires": [_serialize_recipient(user)]}), 200

    # ==========================================================
    # CAS 2 : TARGET "NIVEAU" - Tous les utilisateurs d'un niveau
    # ==========================================================

    elif target_type == "niveau":
        if not target_id:
            return jsonify({"message": "target_id requis pour le type 'niveau'"}), 400

        niveau = db.session.get(Niveau, target_id)
        if not niveau:
            return jsonify({"message": "Niveau introuvable"}), 404

        # ------------------------------------------------------
        # Vérification des autorisations
        # ------------------------------------------------------
        # "ordre" : plus petit = niveau hiérarchique plus élevé (ex :
        # Directeur Général = 1, Agent = 5). La règle métier "on ne
        # peut cibler que des niveaux inférieurs" signifie donc que
        # l'ordre CIBLE doit être STRICTEMENT SUPÉRIEUR à l'ordre
        # courant. La version précédente testait l'inverse
        # (`ordre_cible >= ordre_courant` -> refus), ce qui interdisait
        # en pratique de cibler des niveaux inférieurs et autorisait
        # de cibler des niveaux supérieurs : c'était l'exact opposé de
        # la règle voulue (correctif sécurité majeur).

        if not current_user.est_administrateur_systeme and current_user.niveau:
            ordre_courant = current_user.niveau.ordre
            ordre_cible = niveau.ordre

            if ordre_cible <= ordre_courant:
                return jsonify({
                    "message": "Vous ne pouvez envoyer qu'à des niveaux hiérarchiquement inférieurs"
                }), 403

        # ------------------------------------------------------
        # Déterminer et valider la structure
        # ------------------------------------------------------
        # Correctif : la structure fournie par le client n'était pas
        # bornée. N'importe quel utilisateur authentifié pouvait
        # cibler une structure hors de son périmètre en la passant
        # explicitement dans le corps de la requête.

        if structure_id:
            structure = db.session.get(Structure, structure_id)
            if not structure:
                return jsonify({"message": "Structure introuvable"}), 404

            if not current_user.est_administrateur_systeme:
                mes_structures = get_descendant_structure_ids(current_user.structure_id)
                if structure_id not in mes_structures:
                    return jsonify({
                        "message": "Vous ne pouvez cibler que votre structure "
                                   "ou une structure descendante"
                    }), 403
        else:
            structure_id = current_user.structure_id

        descendant_ids = get_descendant_structure_ids(structure_id)

        users = User.query.filter(
            User.niveau_id == target_id,
            User.structure_id.in_(descendant_ids),
            User.statut == Statut.ACTIF,
            User.id != current_user_id
        ).all()

        # Correctif : un destinataire sans clé publique (compte actif
        # mais jamais "vraiment" activé côté crypto — cas résiduel des
        # comptes historiques) faisait échouer TOUT l'envoi côté
        # navigateur (chiffrement RSA-OAEP impossible sans clé). On
        # les exclut ici et on le signale, plutôt que de laisser
        # échouer un envoi à 50 personnes à cause d'une seule d'entre
        # elles.
        utilisables = [u for u in users if u.cle_publique]
        ignores = len(users) - len(utilisables)

        if not utilisables:
            return jsonify({
                "message": "Aucun utilisateur exploitable trouvé pour ce niveau "
                           "dans cette structure (aucun compte actif avec une "
                           "clé de chiffrement)"
            }), 404

        return jsonify({
            "destinataires": [_serialize_recipient(u) for u in utilisables],
            "destinataires_ignores_sans_cle": ignores
        }), 200

    # ==========================================================
    # CAS 3 : TARGET "ALL" - Tous les utilisateurs
    # ==========================================================

    elif target_type == "all":
        est_autorise = current_user.est_administrateur_systeme or (
            current_user.niveau and current_user.niveau.ordre == 1
        )

        if not est_autorise:
            return jsonify({
                "message": "Seuls l'administrateur système ou le niveau le "
                           "plus élevé peuvent diffuser à tous"
            }), 403

        users = User.query.filter(
            User.statut == Statut.ACTIF,
            User.id != current_user_id
        ).all()

        utilisables = [u for u in users if u.cle_publique]
        ignores = len(users) - len(utilisables)

        return jsonify({
            "destinataires": [_serialize_recipient(u) for u in utilisables],
            "destinataires_ignores_sans_cle": ignores
        }), 200

    else:
        return jsonify({"message": f"Type de cible inconnu : {target_type}"}), 400
