# backend/app/routes/auth_routes.py
import uuid

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity
)

from app import db, limiter
from app.models import User, Statut, Invitation
from app.services.auth_service import (
    verify_password,
    hash_password,
    is_password_strong_enough,
    generate_invitation_token,
    hash_invitation_token,
    invitation_expiration,
    is_invitation_expired,
    generate_recovery_code,
    hash_recovery_code,
    PBKDF2_ITERATIONS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MAX_BYTES,
)
from app.services.email_service import send_invitation_email, send_security_notification
from app.services.history_service import log_action
from app.services.security_service import (
    normalize_email,
    is_valid_public_key_b64,
    is_valid_salt_b64,
    is_valid_private_bundle_b64,
)


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


def _password_policy_message():
    return (
        f"Le mot de passe doit contenir entre {PASSWORD_MIN_LENGTH} et "
        f"{PASSWORD_MAX_BYTES} caractères, dont au moins une lettre et un chiffre"
    )


def _issue_token(user):
    """
    Émet un JWT en y embarquant l'"epoch" courant de l'utilisateur.
    Cette valeur est comparée à celle en base à chaque requête protégée
    (cf. token_in_blocklist_loader dans app/__init__.py) : un changement
    de mot de passe ou une désactivation invalide donc IMMÉDIATEMENT
    tous les tokens émis avant l'incrément, sans attendre 8h.
    """
    return create_access_token(
        identity=user.id,
        additional_claims={"epoch": user.jwt_epoch}
    )


def _user_public_payload(user):
    return {
        "id": user.id,
        "nom": user.nom,
        "prenom": user.prenom,
        "email": user.email,
        "poste_administratif": user.poste_administratif,
        "niveau_id": user.niveau_id,
        "structure_id": user.structure_id,
        "est_administrateur_systeme": user.est_administrateur_systeme
    }


# ================================================================
# ROUTE : LOGIN
# ================================================================
#
# Note sur l'énumération de comptes : pour un compte EN_ATTENTE, AUCUN
# mot de passe n'existe encore en base (mot_de_passe_hash est NULL) —
# il n'existe donc aucun moyen de faire dépendre le message d'un
# mot de passe "correct", puisqu'aucun n'est défini. Le message
# "compte non activé" révèle donc structurellement qu'un email est
# enregistré. C'est un compromis assumé et documenté (cf. README) :
# la limitation de débit ci-dessous réduit la portée d'un balayage.
# En revanche, pour un compte ACTIF ou INACTIF, le mot de passe existe
# : on le vérifie AVANT de révéler le statut, pour qu'un tiers sans le
# mot de passe ne puisse pas distinguer "email inconnu" de "compte
# désactivé" simplement en devinant des adresses.
#
@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():

    data = request.get_json() or {}

    email = normalize_email(data.get("email"))
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email et mot de passe requis"}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"message": "Identifiants invalides"}), 401

    if user.statut == Statut.EN_ATTENTE:
        # Voir note ci-dessus : ce cas ne peut pas passer par une
        # vérification de mot de passe (il n'y en a pas encore).
        return jsonify({
            "message": "Ce compte n'a pas encore été activé. "
                       "Utilisez le lien d'invitation reçu par email."
        }), 403

    mot_de_passe_valide = verify_password(password, user.mot_de_passe_hash)

    if not mot_de_passe_valide:
        log_action(user.id, "CONNEXION", statut_action=False)
        db.session.commit()
        return jsonify({"message": "Identifiants invalides"}), 401

    if user.statut != Statut.ACTIF:
        # Mot de passe correct mais compte désactivé : on ne révèle ce
        # statut qu'APRÈS avoir vérifié le mot de passe, pour qu'un
        # tiers ne puisse pas confirmer l'existence d'un compte
        # désactivé sans le connaître.
        log_action(user.id, "CONNEXION", statut_action=False)
        db.session.commit()
        return jsonify({"message": "Compte désactivé"}), 403

    token = _issue_token(user)

    log_action(user.id, "CONNEXION", statut_action=True)
    db.session.commit()

    return jsonify({
        "access_token": token,
        "user": _user_public_payload(user),
        "cle_publique": user.cle_publique,
        "cle_publique_signature": user.cle_publique_signature,
        "cle_privee_chiffree": user.cle_privee_chiffree,
        "sel_derivation_cle": user.sel_derivation_cle,
        "pbkdf2_iterations": user.pbkdf2_iterations,
    }), 200


# ================================================================
# ROUTE : PROFIL DE L'UTILISATEUR CONNECTE
# ================================================================

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, get_jwt_identity())

    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    return jsonify({
        "user": _user_public_payload(user),
        "cle_publique": user.cle_publique,
        "cle_publique_signature": user.cle_publique_signature,
        "cle_privee_chiffree": user.cle_privee_chiffree,
        "sel_derivation_cle": user.sel_derivation_cle,
        "pbkdf2_iterations": user.pbkdf2_iterations,
    }), 200


# ================================================================
# ROUTE : VERIFIER UN LIEN D'INVITATION
# ================================================================

@auth_bp.route("/verify-invitation", methods=["POST"])
@limiter.limit("20 per minute")
def verify_invitation():
    data = request.get_json() or {}
    email = normalize_email(data.get("email"))
    token = data.get("token")

    if not email or not token:
        return jsonify({"message": "Email et token requis"}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"message": "Lien d'invitation invalide"}), 404

    if user.statut != Statut.EN_ATTENTE:
        return jsonify({"message": "Ce compte est déjà actif ou désactivé"}), 400

    token_hash = hash_invitation_token(token)

    invitation = Invitation.query.filter_by(
        utilisateur_id=user.id,
        token_hash=token_hash,
        utilise=False
    ).order_by(Invitation.date_creation.desc()).first()

    if not invitation:
        return jsonify({"message": "Lien d'invitation invalide ou déjà utilisé"}), 404

    if is_invitation_expired(invitation.date_expiration):
        return jsonify({
            "message": "Ce lien d'invitation a expiré. "
                       "Demandez à un administrateur de vous en renvoyer un."
        }), 410

    return jsonify({
        "valid": True,
        "email": user.email,
        "nom": user.nom,
        "prenom": user.prenom
    }), 200


# ================================================================
# ROUTE : ACTIVER LE COMPTE
# ================================================================
# Le navigateur génère DEUX paires de clés RSA-2048 (une pour le
# chiffrement RSA-OAEP, une pour la signature RSA-PSS), les regroupe
# dans un blob JSON qu'il chiffre en AES-GCM avec une clé dérivée du
# mot de passe (PBKDF2, 600 000 itérations), et génère en plus un
# CODE DE RÉCUPÉRATION affiché une seule fois : ce même blob de clés
# privées est aussi chiffré avec une clé dérivée de ce code, pour
# permettre une réinitialisation de mot de passe sans admin ni perte
# des fichiers déjà reçus.
# ================================================================

@auth_bp.route("/activate-account", methods=["POST"])
@limiter.limit("10 per minute")
def activate_account():
    data = request.get_json() or {}

    email = normalize_email(data.get("email"))
    token = data.get("token")
    password = data.get("password")
    public_key = data.get("publicKey")
    public_key_signature = data.get("publicKeySignature")
    encrypted_private_key = data.get("encryptedPrivateKey")
    salt = data.get("salt")
    pbkdf2_iterations = data.get("pbkdf2Iterations", PBKDF2_ITERATIONS)
    recovery_encrypted_private_key = data.get("recoveryEncryptedPrivateKey")
    recovery_salt = data.get("recoverySalt")
    recovery_code_hash = data.get("recoveryCodeHash")

    required = [
        email, token, password, public_key, public_key_signature,
        encrypted_private_key, salt, recovery_encrypted_private_key,
        recovery_salt, recovery_code_hash
    ]
    if not all(required):
        return jsonify({"message": "Tous les champs sont requis"}), 400

    if not is_password_strong_enough(password):
        return jsonify({"message": _password_policy_message()}), 400

    if not is_valid_public_key_b64(public_key) or not is_valid_public_key_b64(public_key_signature):
        return jsonify({
            "message": "Clé publique invalide (format ou taille inattendue)"
        }), 400

    if not is_valid_salt_b64(salt) or not is_valid_salt_b64(recovery_salt):
        return jsonify({"message": "Sel de dérivation invalide"}), 400

    if not is_valid_private_bundle_b64(encrypted_private_key) or \
            not is_valid_private_bundle_b64(recovery_encrypted_private_key):
        return jsonify({"message": "Clé privée chiffrée invalide"}), 400

    if not isinstance(recovery_code_hash, str) or len(recovery_code_hash) != 64:
        return jsonify({"message": "Empreinte du code de récupération invalide"}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    if user.statut != Statut.EN_ATTENTE:
        return jsonify({"message": "Ce compte est déjà actif ou désactivé"}), 400

    token_hash = hash_invitation_token(token)

    invitation = Invitation.query.filter_by(
        utilisateur_id=user.id,
        token_hash=token_hash,
        utilise=False
    ).order_by(Invitation.date_creation.desc()).first()

    if not invitation:
        return jsonify({"message": "Lien d'invitation invalide ou déjà utilisé"}), 404

    if is_invitation_expired(invitation.date_expiration):
        return jsonify({"message": "Ce lien d'invitation a expiré"}), 410

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    user.mot_de_passe_hash = password_hash
    user.cle_publique = public_key
    user.cle_publique_signature = public_key_signature
    user.cle_privee_chiffree = encrypted_private_key
    user.sel_derivation_cle = salt
    user.pbkdf2_iterations = int(pbkdf2_iterations)
    user.cle_privee_chiffree_recovery = recovery_encrypted_private_key
    user.sel_recovery = recovery_salt
    user.recovery_code_hash = recovery_code_hash
    user.statut = Statut.ACTIF

    invitation.utilise = True

    log_action(user.id, "ACTIVATION_COMPTE", statut_action=True)

    db.session.commit()

    return jsonify({"message": "Compte activé avec succès"}), 200


# ================================================================
# ROUTE : CHANGER SON MOT DE PASSE (utilisateur connecté)
# ================================================================

@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
@limiter.limit("10 per minute")
def change_password():
    user = db.session.get(User, get_jwt_identity())

    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404

    data = request.get_json() or {}

    current_password = data.get("current_password")
    new_password = data.get("new_password")
    new_encrypted_private_key = data.get("encryptedPrivateKey")
    new_salt = data.get("salt")
    pbkdf2_iterations = data.get("pbkdf2Iterations", PBKDF2_ITERATIONS)

    if not all([current_password, new_password, new_encrypted_private_key, new_salt]):
        return jsonify({"message": "Tous les champs sont requis"}), 400

    if not verify_password(current_password, user.mot_de_passe_hash):
        return jsonify({"message": "Mot de passe actuel incorrect"}), 401

    if not is_password_strong_enough(new_password):
        return jsonify({"message": _password_policy_message()}), 400

    if not is_valid_salt_b64(new_salt) or not is_valid_private_bundle_b64(new_encrypted_private_key):
        return jsonify({"message": "Clé privée chiffrée ou sel invalide"}), 400

    try:
        user.mot_de_passe_hash = hash_password(new_password)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    user.cle_privee_chiffree = new_encrypted_private_key
    user.sel_derivation_cle = new_salt
    user.pbkdf2_iterations = int(pbkdf2_iterations)

    # Invalide tous les JWT déjà émis pour ce compte : sans ça, un
    # attaquant ayant volé un ancien token continuerait d'y avoir
    # accès jusqu'à son expiration naturelle malgré le changement de
    # mot de passe.
    user.jwt_epoch = (user.jwt_epoch or 0) + 1

    log_action(user.id, "CHANGEMENT_MOT_DE_PASSE", statut_action=True)

    db.session.commit()

    send_security_notification(
        user.email, user.nom, user.prenom,
        "Mot de passe modifié",
        "Le mot de passe de votre compte vient d'être changé."
    )

    new_token = _issue_token(user)

    return jsonify({
        "message": "Mot de passe modifié avec succès",
        "access_token": new_token
    }), 200


# ================================================================
# ROUTE : DEMANDER LA RÉCUPÉRATION D'UN COMPTE (mot de passe oublié)
# ================================================================
# Étape 1 : le navigateur envoie l'email + le code de récupération
# (jamais transmis au serveur avant cet instant). Si les deux
# correspondent, le serveur renvoie le blob de clés chiffré pour
# récupération + son sel, afin que le navigateur puisse localement
# déchiffrer les clés privées et les rechiffrer avec un nouveau mot
# de passe. Le serveur ne voit JAMAIS le code lui permettre de
# déchiffrer quoi que ce soit : il ne fait que comparer une empreinte.
# ================================================================

@auth_bp.route("/forgot-password/verify", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password_verify():
    data = request.get_json() or {}
    email = normalize_email(data.get("email"))
    recovery_code = data.get("recoveryCode")

    if not email or not recovery_code:
        return jsonify({"message": "Email et code de récupération requis"}), 400

    user = User.query.filter_by(email=email).first()

    generic_error = ("Email ou code de récupération invalide, ou aucun code "
                      "de récupération n'a été généré pour ce compte.")

    if not user or user.statut != Statut.ACTIF or not user.recovery_code_hash:
        return jsonify({"message": generic_error}), 404

    if hash_recovery_code(recovery_code) != user.recovery_code_hash:
        log_action(user.id, "ECHEC_RECUPERATION_COMPTE", statut_action=False)
        db.session.commit()
        return jsonify({"message": generic_error}), 404

    return jsonify({
        "email": user.email,
        "cle_privee_chiffree_recovery": user.cle_privee_chiffree_recovery,
        "sel_recovery": user.sel_recovery
    }), 200


# ================================================================
# ROUTE : FINALISER LA RÉCUPÉRATION (nouveau mot de passe)
# ================================================================
# Étape 2 : le navigateur a déchiffré les clés privées avec le code,
# généré un nouveau sel + nouveau blob chiffré avec le nouveau mot de
# passe, ET un nouveau blob de récupération chiffré avec un NOUVEAU
# code de récupération (l'ancien code est à usage unique : il est
# invalidé ici, un nouveau doit être régénéré et re-affiché).
# ================================================================

@auth_bp.route("/forgot-password/reset", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password_reset():
    data = request.get_json() or {}
    email = normalize_email(data.get("email"))
    recovery_code = data.get("recoveryCode")
    new_password = data.get("newPassword")
    new_encrypted_private_key = data.get("encryptedPrivateKey")
    new_salt = data.get("salt")
    pbkdf2_iterations = data.get("pbkdf2Iterations", PBKDF2_ITERATIONS)
    new_recovery_encrypted_private_key = data.get("recoveryEncryptedPrivateKey")
    new_recovery_salt = data.get("recoverySalt")
    new_recovery_code_hash = data.get("recoveryCodeHash")

    required = [
        email, recovery_code, new_password, new_encrypted_private_key, new_salt,
        new_recovery_encrypted_private_key, new_recovery_salt, new_recovery_code_hash
    ]
    if not all(required):
        return jsonify({"message": "Tous les champs sont requis"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or user.statut != Statut.ACTIF or not user.recovery_code_hash:
        return jsonify({"message": "Récupération impossible pour ce compte"}), 404

    if hash_recovery_code(recovery_code) != user.recovery_code_hash:
        log_action(user.id, "ECHEC_RECUPERATION_COMPTE", statut_action=False)
        db.session.commit()
        return jsonify({"message": "Code de récupération invalide"}), 403

    if not is_password_strong_enough(new_password):
        return jsonify({"message": _password_policy_message()}), 400

    if not is_valid_salt_b64(new_salt) or not is_valid_private_bundle_b64(new_encrypted_private_key):
        return jsonify({"message": "Clé privée chiffrée ou sel invalide"}), 400

    if not is_valid_salt_b64(new_recovery_salt) or \
            not is_valid_private_bundle_b64(new_recovery_encrypted_private_key):
        return jsonify({"message": "Nouveau blob de récupération invalide"}), 400

    if not isinstance(new_recovery_code_hash, str) or len(new_recovery_code_hash) != 64:
        return jsonify({"message": "Empreinte du nouveau code invalide"}), 400

    try:
        user.mot_de_passe_hash = hash_password(new_password)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    user.cle_privee_chiffree = new_encrypted_private_key
    user.sel_derivation_cle = new_salt
    user.pbkdf2_iterations = int(pbkdf2_iterations)
    user.cle_privee_chiffree_recovery = new_recovery_encrypted_private_key
    user.sel_recovery = new_recovery_salt
    user.recovery_code_hash = new_recovery_code_hash
    user.jwt_epoch = (user.jwt_epoch or 0) + 1

    log_action(user.id, "RECUPERATION_COMPTE", statut_action=True)

    db.session.commit()

    send_security_notification(
        user.email, user.nom, user.prenom,
        "Mot de passe réinitialisé",
        "Votre mot de passe vient d'être réinitialisé à l'aide de votre "
        "code de récupération."
    )

    return jsonify({"message": "Mot de passe réinitialisé avec succès"}), 200
