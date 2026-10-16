# backend/app/routes/admin_routes.py
import os
import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app import db, limiter
from app.models import User, Niveau, Structure, Statut, Invitation
from app.services.authorization_service import get_descendant_structure_ids
from app.services.auth_service import (
    generate_invitation_token,
    invitation_expiration
)
from app.services.email_service import send_invitation_email, send_security_notification
from app.services.history_service import log_action
from app.services.security_service import normalize_email

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/api/admin"
)

# Expose le lien d'activation dans la réponse JSON, pour tester le
# parcours complet sans serveur SMTP réel. FERMÉ PAR DÉFAUT : à
# l'inverse de la version précédente (qui l'activait dès que
# FLASK_DEBUG n'était pas explicitement mis à "0"), cette variable
# est indépendante de FLASK_DEBUG et doit être activée EXPLICITEMENT.
# Ne JAMAIS activer en production : le lien permet d'activer le
# compte à la place de son titulaire.
EXPOSE_ACTIVATION_LINK = os.getenv("EXPOSE_ACTIVATION_LINK_DEV", "0") == "1"


def _serialize_user(u):
    return {
        "id": u.id,
        "nom": u.nom,
        "prenom": u.prenom,
        "email": u.email,
        "poste_administratif": u.poste_administratif,
        "statut": u.statut.value,
        "est_administrateur_systeme": u.est_administrateur_systeme,
        "niveau_id": u.niveau_id,
        "structure_id": u.structure_id,
        "cle_publique_presente": u.cle_publique is not None,
        "a_initialise": u.mot_de_passe_hash is not None
    }


def _check_hierarchy_for_target(current_user, niveau, structure_id):
    """
    Vérifie qu'un utilisateur non-admin peut agir (créer/modifier/
    renvoyer une invitation) sur un compte de ce niveau et cette
    structure. Retourne un message d'erreur (str) si refusé, None
    sinon. Facteur commun entre create_user, update_user et
    resend_invitation (qui ne faisait auparavant AUCUNE de ces
    vérifications).
    """
    if not current_user.niveau:
        return "Votre niveau hiérarchique n'est pas défini"

    # Ordre plus petit = niveau plus élevé : la cible doit avoir un
    # ordre strictement supérieur au sien (= niveau inférieur).
    if niveau.ordre <= current_user.niveau.ordre:
        return "Vous ne pouvez gérer que des comptes de niveau strictement inférieur au vôtre"

    allowed_structures = get_descendant_structure_ids(current_user.structure_id)
    if structure_id not in allowed_structures:
        return "Vous ne pouvez gérer que votre structure ou une structure descendante"

    return None


# ================================================================
# ROUTE 1 : CREER UN COMPTE (PROVISIONNEMENT)
# ================================================================

@admin_bp.route("/users", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")
def create_user():
    current_user_id = get_jwt_identity()
    current_user = db.session.get(User, current_user_id)

    if not current_user:
        return jsonify({"message": "Utilisateur connecté introuvable"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"message": "Aucune donnée reçue"}), 400

    nom = (data.get("nom") or "").strip()
    prenom = (data.get("prenom") or "").strip()
    email = normalize_email(data.get("email"))
    poste_administratif = (data.get("poste_administratif") or "").strip()
    niveau_id = data.get("niveau_id")
    structure_id = data.get("structure_id")

    if not all([nom, prenom, email, poste_administratif, niveau_id, structure_id]):
        return jsonify({"message": "Tous les champs sont obligatoires"}), 400

    if "@" not in email or len(email) > 150:
        return jsonify({"message": "Adresse email invalide"}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"message": "Cet email existe déjà"}), 409

    niveau = db.session.get(Niveau, niveau_id)
    if not niveau:
        return jsonify({"message": "Niveau introuvable"}), 404

    structure = db.session.get(Structure, structure_id)
    if not structure:
        return jsonify({"message": "Structure introuvable"}), 404

    if not current_user.est_administrateur_systeme:
        erreur = _check_hierarchy_for_target(current_user, niveau, structure_id)
        if erreur:
            return jsonify({"message": erreur}), 403

    user_id = f"USR-{uuid.uuid4()}"

    user = User(
        id=user_id,
        nom=nom,
        prenom=prenom,
        email=email,
        poste_administratif=poste_administratif,
        est_administrateur_systeme=False,
        statut=Statut.EN_ATTENTE,
        niveau_id=niveau_id,
        structure_id=structure_id,
        mot_de_passe_hash=None,
        cle_publique=None,
        cle_publique_signature=None,
        cle_privee_chiffree=None,
        sel_derivation_cle=None
    )

    db.session.add(user)

    token_en_clair, token_hash = generate_invitation_token()

    invitation = Invitation(
        id=f"INV-{uuid.uuid4()}",
        utilisateur_id=user_id,
        token_hash=token_hash,
        date_expiration=invitation_expiration(),
        utilise=False
    )

    db.session.add(invitation)

    log_action(current_user.id, "CREATION_COMPTE", statut_action=True,
               cible_utilisateur_id=user_id)

    db.session.commit()

    activation_link = send_invitation_email(email, nom, prenom, token_en_clair)

    response = {
        "message": "Compte créé avec succès, invitation envoyée",
        "user": _serialize_user(user)
    }

    if EXPOSE_ACTIVATION_LINK:
        response["lien_activation_dev"] = activation_link

    return jsonify(response), 201


# ================================================================
# ROUTE 2 : LISTER LES UTILISATEURS
# ================================================================

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def list_users():
    current_user_id = get_jwt_identity()
    current_user = db.session.get(User, current_user_id)

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    est_admin = current_user.est_administrateur_systeme
    query = User.query

    if not est_admin:
        descendant_ids = get_descendant_structure_ids(current_user.structure_id)
        query = query.filter(User.structure_id.in_(descendant_ids))

        if current_user.niveau:
            ordre_courant = current_user.niveau.ordre
            query = query.filter(
                User.niveau.has(Niveau.ordre > ordre_courant)
            )

    niveau_id = request.args.get("niveau_id")
    if niveau_id:
        query = query.filter_by(niveau_id=niveau_id)

    structure_id = request.args.get("structure_id")
    if structure_id:
        query = query.filter_by(structure_id=structure_id)

    statut = request.args.get("statut")
    if statut:
        query = query.filter_by(statut=statut)

    search = request.args.get("search")
    if search:
        query = query.filter(
            or_(
                User.nom.ilike(f"%{search}%"),
                User.prenom.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    users = query.order_by(User.nom.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "utilisateurs": [_serialize_user(u) for u in users.items],
        "page": users.page,
        "total_pages": users.pages,
        "total": users.total
    }), 200


# ================================================================
# ROUTE 3 : DETAIL D'UN UTILISATEUR
# ================================================================

@admin_bp.route("/users/<user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    current_user = db.session.get(User, get_jwt_identity())
    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur cible introuvable"}), 404

    if not current_user.est_administrateur_systeme:
        descendant_ids = get_descendant_structure_ids(current_user.structure_id)
        if user.structure_id not in descendant_ids:
            return jsonify({
                "message": "Vous n'êtes pas autorisé à consulter ce compte"
            }), 403

    return jsonify({"user": _serialize_user(user)}), 200


# ================================================================
# ROUTE 4 : MODIFIER UN UTILISATEUR
# ================================================================

@admin_bp.route("/users/<user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    current_user_id = get_jwt_identity()
    current_user = db.session.get(User, current_user_id)

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur cible introuvable"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"message": "Aucune donnée reçue"}), 400

    est_admin = current_user.est_administrateur_systeme

    if not est_admin:
        descendant_ids = get_descendant_structure_ids(current_user.structure_id)
        if user.structure_id not in descendant_ids:
            return jsonify({
                "message": "Vous ne pouvez modifier que votre structure ou une structure descendante"
            }), 403

        if current_user.niveau and user.niveau:
            if user.niveau.ordre <= current_user.niveau.ordre:
                return jsonify({
                    "message": "Vous ne pouvez modifier que des comptes de niveau inférieur au vôtre"
                }), 403

    if "nom" in data:
        user.nom = (data["nom"] or "").strip() or user.nom

    if "prenom" in data:
        user.prenom = (data["prenom"] or "").strip() or user.prenom

    if "email" in data:
        new_email = normalize_email(data["email"])
        if not new_email or "@" not in new_email:
            return jsonify({"message": "Adresse email invalide"}), 400
        existing = User.query.filter(
            User.email == new_email,
            User.id != user_id
        ).first()
        if existing:
            return jsonify({"message": "Cet email est déjà utilisé"}), 409
        user.email = new_email

    if "poste_administratif" in data:
        user.poste_administratif = (data["poste_administratif"] or "").strip() or user.poste_administratif

    if "niveau_id" in data:
        niveau = db.session.get(Niveau, data["niveau_id"])
        if not niveau:
            return jsonify({"message": "Niveau introuvable"}), 404
        if not est_admin and niveau.ordre <= current_user.niveau.ordre:
            return jsonify({
                "message": "Vous ne pouvez assigner qu'un niveau inférieur au vôtre"
            }), 403
        user.niveau_id = data["niveau_id"]

    if "structure_id" in data:
        structure = db.session.get(Structure, data["structure_id"])
        if not structure:
            return jsonify({"message": "Structure introuvable"}), 404
        if not est_admin:
            descendant_ids = get_descendant_structure_ids(current_user.structure_id)
            if data["structure_id"] not in descendant_ids:
                return jsonify({
                    "message": "Vous ne pouvez assigner qu'une structure que vous gérez"
                }), 403
        user.structure_id = data["structure_id"]

    if "est_administrateur_systeme" in data:
        if est_admin:
            user.est_administrateur_systeme = data["est_administrateur_systeme"]
        else:
            return jsonify({
                "message": "Seul un administrateur système peut modifier ce statut"
            }), 403

    if "statut" in data:
        if not est_admin:
            return jsonify({
                "message": "Seul un administrateur système peut modifier le statut"
            }), 403
        try:
            nouveau_statut = Statut(data["statut"])
        except ValueError:
            return jsonify({"message": "Statut invalide"}), 400

        # On ne peut pas faire passer un compte à ACTIF "à la main" :
        # ACTIF exige d'être passé par l'activation (génération des
        # clés). Sans ce garde-fou, un admin pouvait forcer statut=
        # ACTIF sur un compte sans clé publique, qui restait ensuite
        # incapable de recevoir le moindre fichier chiffré.
        if nouveau_statut == Statut.ACTIF and user.statut != Statut.ACTIF \
                and not user.cle_publique:
            return jsonify({
                "message": "Impossible d'activer directement ce compte : il "
                           "doit passer par le lien d'invitation (génération "
                           "des clés). Utilisez « Renvoyer l'invitation »."
            }), 409

        if nouveau_statut == Statut.INACTIF and user.statut != Statut.INACTIF:
            user.jwt_epoch = (user.jwt_epoch or 0) + 1

        user.statut = nouveau_statut

    log_action(current_user.id, "MODIFICATION_COMPTE", statut_action=True,
               cible_utilisateur_id=user.id)

    db.session.commit()

    return jsonify({
        "message": "Utilisateur modifié avec succès",
        "user": _serialize_user(user)
    }), 200


# ================================================================
# ROUTE 5 : ACTIVER UN UTILISATEUR (reactivation manuelle par admin)
# ================================================================

@admin_bp.route("/users/<user_id>/activate", methods=["POST"])
@jwt_required()
def activate_user(user_id):
    current_user = db.session.get(User, get_jwt_identity())

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not current_user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut activer un compte"
        }), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if user.statut == Statut.ACTIF:
        return jsonify({"message": f"L'utilisateur {user.email} est déjà actif"}), 400

    if user.statut == Statut.EN_ATTENTE:
        return jsonify({
            "message": "Ce compte n'a pas encore été activé par son titulaire "
                       "(en attente d'ouverture du lien d'invitation)"
        }), 400

    if not user.cle_publique:
        return jsonify({
            "message": "Ce compte n'a pas de clé publique : réactivation "
                       "impossible sans repasser par une invitation"
        }), 409

    user.statut = Statut.ACTIF

    log_action(current_user.id, "REACTIVATION_COMPTE", statut_action=True,
               cible_utilisateur_id=user.id)

    db.session.commit()

    return jsonify({
        "message": f"L'utilisateur {user.email} a été activé",
        "user": _serialize_user(user)
    }), 200


# ================================================================
# ROUTE 6 : DESACTIVER UN UTILISATEUR (soft delete)
# ================================================================

@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@jwt_required()
def deactivate_user(user_id):
    current_user = db.session.get(User, get_jwt_identity())

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not current_user.est_administrateur_systeme:
        return jsonify({
            "message": "Seul un administrateur système peut désactiver un compte"
        }), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if user.id == current_user.id:
        return jsonify({
            "message": "Vous ne pouvez pas désactiver votre propre compte"
        }), 403

    if user.statut == Statut.INACTIF:
        return jsonify({"message": f"L'utilisateur {user.email} est déjà inactif"}), 400

    user.statut = Statut.INACTIF
    # Invalide immédiatement toute session ouverte de ce compte (cf.
    # token_in_blocklist_loader) : avant ce correctif, un JWT déjà
    # émis restait utilisable jusqu'à 8h après la désactivation.
    user.jwt_epoch = (user.jwt_epoch or 0) + 1

    log_action(current_user.id, "DESACTIVATION_COMPTE", statut_action=True,
               cible_utilisateur_id=user.id)

    db.session.commit()

    return jsonify({
        "message": f"L'utilisateur {user.email} a été désactivé",
        "user": _serialize_user(user)
    }), 200


# ================================================================
# ROUTE 7 : RENVOYER UNE INVITATION (compte EN_ATTENTE uniquement)
# ================================================================

@admin_bp.route("/users/<user_id>/resend-invitation", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def resend_invitation(user_id):
    current_user = db.session.get(User, get_jwt_identity())

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if not current_user.est_administrateur_systeme:
        # Correctif : auparavant, seule l'appartenance à la structure
        # descendante était vérifiée, pas le NIVEAU. Un "Responsable"
        # pouvait ainsi régénérer le lien d'un compte "Directeur" en
        # attente (prise de contrôle potentielle d'un compte
        # hiérarchiquement supérieur).
        erreur = _check_hierarchy_for_target(current_user, user.niveau, user.structure_id)
        if erreur:
            return jsonify({"message": erreur}), 403

    if user.statut != Statut.EN_ATTENTE:
        return jsonify({
            "message": "Ce compte est déjà actif, aucune invitation à renvoyer"
        }), 400

    Invitation.query.filter_by(
        utilisateur_id=user.id, utilise=False
    ).update({"utilise": True})

    token_en_clair, token_hash = generate_invitation_token()

    invitation = Invitation(
        id=f"INV-{uuid.uuid4()}",
        utilisateur_id=user.id,
        token_hash=token_hash,
        date_expiration=invitation_expiration(),
        utilise=False
    )
    db.session.add(invitation)

    log_action(current_user.id, "RENVOI_INVITATION", statut_action=True,
               cible_utilisateur_id=user.id)

    db.session.commit()

    activation_link = send_invitation_email(user.email, user.nom, user.prenom, token_en_clair)

    response = {"message": "Invitation renvoyée avec succès"}
    if EXPOSE_ACTIVATION_LINK:
        response["lien_activation_dev"] = activation_link

    return jsonify(response), 200


# ================================================================
# ROUTE 8 : SUPPRIMER UN COMPTE EN_ATTENTE (jamais activé)
# ================================================================
# Auparavant, une erreur de saisie à la création (email fautif) ne
# pouvait ni être supprimée ni renvoyée à la bonne adresse sans
# passer par la base de données directement.
# ================================================================

@admin_bp.route("/users/<user_id>", methods=["DELETE"])
@jwt_required()
def delete_pending_user(user_id):
    current_user = db.session.get(User, get_jwt_identity())

    if not current_user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if user.statut != Statut.EN_ATTENTE:
        return jsonify({
            "message": "Seul un compte jamais activé (EN_ATTENTE) peut être supprimé. "
                       "Désactivez plutôt un compte déjà activé."
        }), 409

    if not current_user.est_administrateur_systeme:
        erreur = _check_hierarchy_for_target(current_user, user.niveau, user.structure_id)
        if erreur:
            return jsonify({"message": erreur}), 403

    Invitation.query.filter_by(utilisateur_id=user.id).delete()

    email = user.email
    log_action(current_user.id, "SUPPRESSION_COMPTE_EN_ATTENTE", statut_action=True,
               detail=f"Compte supprimé : {email}")

    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": f"Le compte en attente {email} a été supprimé"}), 200
