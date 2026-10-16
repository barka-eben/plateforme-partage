# backend/app/routes/file_routes.py
import json
import uuid
import base64
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db, limiter
from app.models import User, Fichier, Diffusion, Historique, Niveau, Statut
from app.services.authorization_service import get_descendant_structure_ids
from app.services.history_service import log_action


file_bp = Blueprint(
    "files",
    __name__,
    url_prefix="/api/files"
)


def _check_broadcast_authorization(expediteur, mode, target_niveau_id, target_structure_id):
    """
    Reproduit côté serveur, au moment de l'UPLOAD, les mêmes règles
    que /api/targets/resolve pour les modes "niveau" et "all".

    Correctif majeur : auparavant, /targets/resolve appliquait des
    règles hiérarchiques, mais RIEN n'empêchait le navigateur d'appeler
    directement /files/upload avec n'importe quelle liste de
    destinataires, en contournant totalement /targets/resolve. Un
    "Agent" pouvait ainsi déposer un fichier visant un "Directeur"
    sans jamais passer par la vérification. Le mode "user" (envoi à
    une personne précise) reste volontairement libre, conformément à
    la règle métier documentée ailleurs dans le code.

    Retourne un message d'erreur (str) si refusé, None si autorisé.
    """
    if mode == "user":
        return None

    if expediteur.est_administrateur_systeme:
        return None

    if mode == "all":
        if expediteur.niveau and expediteur.niveau.ordre == 1:
            return None
        return "Seuls l'administrateur système ou le niveau le plus élevé peuvent diffuser à tous"

    if mode == "niveau":
        if not target_niveau_id:
            return "target_niveau_id requis pour le mode 'niveau'"

        niveau = db.session.get(Niveau, target_niveau_id)
        if not niveau:
            return "Niveau cible introuvable"

        if expediteur.niveau and niveau.ordre <= expediteur.niveau.ordre:
            return "Vous ne pouvez diffuser qu'à des niveaux hiérarchiquement inférieurs"

        structure_id = target_structure_id or expediteur.structure_id
        mes_structures = get_descendant_structure_ids(expediteur.structure_id)
        if structure_id not in mes_structures:
            return "Vous ne pouvez diffuser que dans votre structure ou une structure descendante"

        return None

    return f"Mode de diffusion inconnu : {mode}"


# ================================================================
# ROUTE 1 : UPLOAD
# ================================================================

@file_bp.route("/upload", methods=["POST"])
@jwt_required()
@limiter.limit("20 per minute")
def upload_file():
    """
    Réception d'un fichier déjà chiffré côté navigateur.

    Contrat attendu (multipart/form-data) :
      - file                        : contenu binaire déjà chiffré (AES-GCM)
      - hash_sha256                 : hash SHA-256 du fichier AVANT chiffrement (hex)
      - signature                   : signature RSA-PSS de ce hash (base64)
      - nom_chiffre                 : nom de fichier tel que fourni par le client
      - cle_aes_chiffree_expediteur : clé AES chiffrée pour l'expéditeur lui-même
      - diffusions                  : JSON [{"destinataire_id", "cle_aes_chiffree"}, ...]
      - mode                        : "user" | "niveau" | "all" (pour l'autorisation serveur)
      - target_niveau_id, target_structure_id : requis si mode == "niveau"
    """

    user_id = get_jwt_identity()
    expediteur = db.session.get(User, user_id)

    if not expediteur:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if "file" not in request.files:
        return jsonify({"message": "Aucun fichier envoyé"}), 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return jsonify({"message": "Nom de fichier invalide"}), 400

    donnee_chiffree = uploaded_file.read()

    if not donnee_chiffree:
        return jsonify({"message": "Le fichier envoyé est vide"}), 400

    hash_sha256 = request.form.get("hash_sha256")
    signature = request.form.get("signature")
    nom_chiffre = request.form.get("nom_chiffre")
    diffusions_raw = request.form.get("diffusions")
    cle_aes_chiffree_expediteur = request.form.get("cle_aes_chiffree_expediteur")
    mode = request.form.get("mode", "user")
    target_niveau_id = request.form.get("target_niveau_id")
    target_structure_id = request.form.get("target_structure_id")

    if not all([hash_sha256, signature, nom_chiffre, diffusions_raw, cle_aes_chiffree_expediteur]):
        return jsonify({
            "message": "Champs manquants : hash_sha256, signature, nom_chiffre, "
                       "cle_aes_chiffree_expediteur et diffusions sont obligatoires"
        }), 400

    if len(hash_sha256) != 64:
        return jsonify({"message": "hash_sha256 invalide (doit faire 64 caractères hex)"}), 400

    erreur_autorisation = _check_broadcast_authorization(
        expediteur, mode, target_niveau_id, target_structure_id
    )
    if erreur_autorisation:
        return jsonify({"message": erreur_autorisation}), 403

    try:
        diffusions_demandees = json.loads(diffusions_raw)
    except (TypeError, ValueError):
        return jsonify({"message": "Le champ diffusions n'est pas un JSON valide"}), 400

    if not isinstance(diffusions_demandees, list) or not diffusions_demandees:
        return jsonify({"message": "diffusions doit être une liste non vide de destinataires"}), 400

    destinataires_ids = []

    for entree in diffusions_demandees:
        if not isinstance(entree, dict):
            return jsonify({"message": "Chaque entrée de diffusions doit être un objet"}), 400

        destinataire_id = entree.get("destinataire_id")
        cle_aes_chiffree = entree.get("cle_aes_chiffree")

        if not destinataire_id or not cle_aes_chiffree:
            return jsonify({
                "message": "Chaque diffusion nécessite destinataire_id et cle_aes_chiffree"
            }), 400

        destinataires_ids.append(destinataire_id)

    utilisateurs_trouves = User.query.filter(User.id.in_(destinataires_ids)).all()
    ids_trouves = {u.id for u in utilisateurs_trouves}
    ids_manquants = set(destinataires_ids) - ids_trouves

    if ids_manquants:
        return jsonify({
            "message": "Destinataire(s) introuvable(s)",
            "destinataires_introuvables": list(ids_manquants)
        }), 404

    # Pour le mode "niveau", vérifie en plus que CHAQUE destinataire
    # appartient bien au niveau/structure annoncés (empêche de glisser
    # un destinataire hors périmètre dans une requête par ailleurs
    # valide).
    if mode == "niveau" and not expediteur.est_administrateur_systeme:
        structure_id = target_structure_id or expediteur.structure_id
        perimetre = set(get_descendant_structure_ids(structure_id))
        for u in utilisateurs_trouves:
            if u.niveau_id != target_niveau_id or u.structure_id not in perimetre:
                return jsonify({
                    "message": f"Le destinataire {u.email} est hors du périmètre "
                               "de diffusion déclaré"
                }), 403

    try:
        fichier = Fichier(
            id=f"FIC-{uuid.uuid4()}",
            nom_chiffre=nom_chiffre,
            hash_sha256=hash_sha256,
            signature=signature,
            donnee_chiffree=donnee_chiffree,
            expediteur_id=expediteur.id,
            cle_aes_chiffree_expediteur=cle_aes_chiffree_expediteur
        )

        db.session.add(fichier)

        for entree in diffusions_demandees:
            diffusion = Diffusion(
                id=f"DIF-{uuid.uuid4()}",
                cle_aes_chiffree=entree["cle_aes_chiffree"],
                statut_lecture=False,
                date_acces=None,
                fichier_id=fichier.id,
                destinataire_id=entree["destinataire_id"]
            )
            db.session.add(diffusion)

        log_action(expediteur.id, "DEPOT_FICHIER", statut_action=True, fichier_id=fichier.id)

        db.session.commit()

    except Exception:
        db.session.rollback()
        return jsonify({"message": "Erreur lors de l'enregistrement du fichier"}), 500

    return jsonify({
        "message": "Fichier déposé avec succès",
        "fichier_id": fichier.id,
        "nombre_destinataires": len(diffusions_demandees)
    }), 201


# ================================================================
# ROUTE 2 : LISTER LES FICHIERS
# ================================================================

@file_bp.route("", methods=["GET"])
@jwt_required()
def list_files():
    user_id = get_jwt_identity()

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    fichiers_envoyes = Fichier.query.filter_by(
        expediteur_id=user_id
    ).order_by(Fichier.date_depot.desc()).all()

    envoyes = []
    for fichier in fichiers_envoyes:
        nb_destinataires = Diffusion.query.filter_by(fichier_id=fichier.id).count()
        nb_lectures = Diffusion.query.filter_by(
            fichier_id=fichier.id, statut_lecture=True
        ).count()

        envoyes.append({
            "id": fichier.id,
            "nom_chiffre": fichier.nom_chiffre,
            "date_depot": fichier.date_depot.isoformat(),
            "hash_sha256": fichier.hash_sha256,
            "nb_destinataires": nb_destinataires,
            "nb_lectures": nb_lectures
        })

    diffusions = Diffusion.query.filter_by(
        destinataire_id=user_id
    ).order_by(Diffusion.date_acces.desc()).all()

    recus = []
    for diffusion in diffusions:
        fichier = diffusion.fichier
        if not fichier:
            continue

        expediteur = db.session.get(User, fichier.expediteur_id)

        recus.append({
            "id": fichier.id,
            "nom_chiffre": fichier.nom_chiffre,
            "date_depot": fichier.date_depot.isoformat(),
            "date_acces": diffusion.date_acces.isoformat() if diffusion.date_acces else None,
            "statut_lecture": diffusion.statut_lecture,
            "expediteur_nom": f"{expediteur.prenom} {expediteur.nom}" if expediteur else "Inconnu",
            "expediteur_id": fichier.expediteur_id
        })

    return jsonify({"envoyes": envoyes, "recus": recus}), 200


# ================================================================
# ROUTE 3 : TÉLÉCHARGER UN FICHIER
# ================================================================

@file_bp.route("/<fichier_id>", methods=["GET"])
@jwt_required()
def get_file(fichier_id):
    user_id = get_jwt_identity()

    fichier = db.session.get(Fichier, fichier_id)
    if not fichier:
        return jsonify({"message": "Fichier introuvable"}), 404

    if fichier.expediteur_id == user_id:
        pass
    else:
        diffusion = Diffusion.query.filter_by(
            fichier_id=fichier_id, destinataire_id=user_id
        ).first()
        if not diffusion:
            return jsonify({"message": "Vous n'êtes pas autorisé à consulter ce fichier"}), 403

    if fichier.expediteur_id == user_id:
        if not fichier.cle_aes_chiffree_expediteur:
            return jsonify({
                "message": "Aucune copie de clé disponible pour l'expéditeur sur ce fichier"
            }), 404
        cle_aes_chiffree = fichier.cle_aes_chiffree_expediteur
    else:
        diffusion = Diffusion.query.filter_by(
            fichier_id=fichier_id, destinataire_id=user_id
        ).first()
        if not diffusion:
            return jsonify({"message": "Vous n'êtes pas destinataire de ce fichier"}), 403

        cle_aes_chiffree = diffusion.cle_aes_chiffree
        diffusion.date_acces = datetime.now(timezone.utc)
        db.session.commit()

    expediteur = db.session.get(User, fichier.expediteur_id)
    if not expediteur:
        return jsonify({"message": "Expéditeur introuvable"}), 404

    donnee_chiffree_b64 = base64.b64encode(fichier.donnee_chiffree).decode("utf-8")

    return jsonify({
        "fichier_id": fichier.id,
        "nom_chiffre": fichier.nom_chiffre,
        "donnee_chiffree": donnee_chiffree_b64,
        "hash_sha256": fichier.hash_sha256,
        "signature": fichier.signature,
        "cle_aes_chiffree": cle_aes_chiffree,
        "cle_publique_expediteur": expediteur.cle_publique_signature,
        "date_depot": fichier.date_depot.isoformat(),
        "expediteur_nom": f"{expediteur.prenom} {expediteur.nom}",
        "est_expediteur": fichier.expediteur_id == user_id
    }), 200


# ================================================================
# ROUTE 4 : MARQUER UN FICHIER COMME LU
# ================================================================

@file_bp.route("/<fichier_id>/mark-read", methods=["PUT"])
@jwt_required()
def mark_file_read(fichier_id):
    user_id = get_jwt_identity()

    fichier = db.session.get(Fichier, fichier_id)
    if not fichier:
        return jsonify({"message": "Fichier introuvable"}), 404

    diffusion = Diffusion.query.filter_by(
        fichier_id=fichier_id, destinataire_id=user_id
    ).first()

    if not diffusion:
        return jsonify({"message": "Vous n'êtes pas destinataire de ce fichier"}), 403

    if not diffusion.statut_lecture:
        diffusion.statut_lecture = True
        diffusion.date_acces = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({
        "message": "Fichier marqué comme lu",
        "statut_lecture": diffusion.statut_lecture
    }), 200


# ================================================================
# ROUTE 5 : CONFIRMER LE RESULTAT D'UN TELECHARGEMENT
# ================================================================

@file_bp.route("/<fichier_id>/confirm-download", methods=["POST"])
@jwt_required()
def confirm_download(fichier_id):
    user_id = get_jwt_identity()

    fichier = db.session.get(Fichier, fichier_id)
    if not fichier:
        return jsonify({"message": "Fichier introuvable"}), 404

    # Correctif : n'importe quel utilisateur connecté pouvait écrire
    # une entrée "ECHEC_VERIFICATION_SIGNATURE" sur N'IMPORTE QUEL
    # fichier, y compris un fichier auquel il n'avait jamais eu accès
    # (pollution du journal d'audit). On vérifie désormais qu'il est
    # bien l'expéditeur ou un destinataire du fichier concerné.
    est_lie = (fichier.expediteur_id == user_id) or Diffusion.query.filter_by(
        fichier_id=fichier_id, destinataire_id=user_id
    ).first() is not None

    if not est_lie:
        return jsonify({
            "message": "Vous n'êtes pas concerné par ce fichier"
        }), 403

    data = request.get_json() or {}
    signature_valide = data.get("signature_valide")

    if signature_valide is None:
        return jsonify({"message": "signature_valide est requis (booleen)"}), 400

    action = "TELECHARGEMENT" if signature_valide else "ECHEC_VERIFICATION_SIGNATURE"

    log_action(
        utilisateur_id=user_id,
        action=action,
        statut_action=bool(signature_valide),
        fichier_id=fichier_id
    )
    db.session.commit()

    return jsonify({"message": "Journalisé"}), 200
