# backend/app/routes/history_routes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

from app import db
from app.models import User, Historique


history_bp = Blueprint(
    "history",
    __name__,
    url_prefix="/api/history"
)


# ================================================================
# ROUTE 1 : HISTORIQUE PERSONNEL
# ================================================================

@history_bp.route("", methods=["GET"])
@jwt_required()
def get_personal_history():
    """
    Récupère l'historique personnel de l'utilisateur connecté.
    
    Retourne les 100 dernières actions de l'utilisateur,
    triées du plus récent au plus ancien.
    """
    
    # 1. Récupérer l'utilisateur connecté
    user_id = get_jwt_identity()
    
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Utilisateur introuvable"}), 404
    
    # 2. Récupérer son historique (100 dernières actions)
    historique = Historique.query.filter_by(
        utilisateur_id=user_id
    ).order_by(Historique.date_action.desc()).limit(100).all()
    
    # 3. Formater la réponse
    return jsonify({
        "historique": [
            {
                "id": h.id,
                "action": h.action,
                "date_action": h.date_action.isoformat(),
                "statut_action": h.statut_action,
                "fichier_id": h.fichier_id
            }
            for h in historique
        ]
    }), 200


# ================================================================
# ROUTE 2 : JOURNAL ADMINISTRATIF (GLOBAL)
# ================================================================

@history_bp.route("/admin/journal", methods=["GET"])
@jwt_required()
def get_admin_journal():
    """
    Récupère le journal global d'activité (admin système uniquement).
    
    Paramètres de filtrage (en query string) :
    - page : numéro de la page (défaut : 1)
    - per_page : nombre d'entrées par page (défaut : 50)
    - action : filtrer par type d'action (ex: "DEPOT_FICHIER")
    - utilisateur_id : filtrer par utilisateur
    - date_debut : filtrer à partir d'une date (format ISO)
    - date_fin : filtrer jusqu'à une date (format ISO)
    """
    
    # 1. Récupérer l'utilisateur connecté
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    
    # 2. Vérifier que c'est un admin système
    if not user or not user.est_administrateur_systeme:
        return jsonify({
            "message": "Accès réservé aux administrateurs système"
        }), 403
    
    # 3. Construire la requête de base
    query = Historique.query
    
    # ==========================================================
    # APPLIQUER LES FILTRES
    # ==========================================================
    
    # Filtrer par type d'action
    action = request.args.get("action")
    if action:
        query = query.filter_by(action=action)
    
    # Filtrer par utilisateur
    utilisateur_id = request.args.get("utilisateur_id")
    if utilisateur_id:
        query = query.filter_by(utilisateur_id=utilisateur_id)
    
    # Filtrer par date de début
    date_debut = request.args.get("date_debut")
    if date_debut:
        try:
            date_debut_parse = datetime.fromisoformat(date_debut)
            query = query.filter(Historique.date_action >= date_debut_parse)
        except ValueError:
            return jsonify({
                "message": "Format de date_debut invalide. Utilisez YYYY-MM-DDTHH:MM:SS"
            }), 400
    
    # Filtrer par date de fin
    date_fin = request.args.get("date_fin")
    if date_fin:
        try:
            date_fin_parse = datetime.fromisoformat(date_fin)
            query = query.filter(Historique.date_action <= date_fin_parse)
        except ValueError:
            return jsonify({
                "message": "Format de date_fin invalide. Utilisez YYYY-MM-DDTHH:MM:SS"
            }), 400
    
    # ==========================================================
    # PAGINATION
    # ==========================================================
    
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    
    historique = query.order_by(
        Historique.date_action.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # ==========================================================
    # CONSTRUIRE LA RÉPONSE AVEC LES INFOS UTILISATEUR
    # ==========================================================
    
    resultats = []
    for h in historique.items:
        user_associe = db.session.get(User, h.utilisateur_id)
        cible = db.session.get(User, h.cible_utilisateur_id) if h.cible_utilisateur_id else None

        resultats.append({
            "id": h.id,
            "action": h.action,
            "date_action": h.date_action.isoformat(),
            "statut_action": h.statut_action,
            "utilisateur": {
                "id": user_associe.id if user_associe else None,
                "nom": user_associe.nom if user_associe else "Inconnu",
                "prenom": user_associe.prenom if user_associe else "Inconnu",
                "email": user_associe.email if user_associe else "Inconnu"
            } if user_associe else None,
            "cible": {
                "id": cible.id,
                "nom": cible.nom,
                "prenom": cible.prenom,
                "email": cible.email
            } if cible else None,
            "ip_adresse": h.ip_adresse,
            "detail": h.detail,
            "fichier_id": h.fichier_id
        })
    
    # 5. Retourner la réponse avec pagination
    return jsonify({
        "journal": resultats,
        "page": historique.page,
        "total_pages": historique.pages,
        "total": historique.total,
        "filtres_appliques": {
            "action": action,
            "utilisateur_id": utilisateur_id,
            "date_debut": date_debut,
            "date_fin": date_fin
        }
    }), 200