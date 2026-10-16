# backend/app/__init__.py
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# ================================================================
# INITIALISATION DES EXTENSIONS
# ================================================================

db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)


def create_app():

    # 1. Créer l'application Flask
    app = Flask(__name__)

    # 2. Charger la configuration
    app.config.from_object("app.config.Config")

    # 3. Initialiser les extensions avec l'application
    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    # ==========================================================
    # 4. CONFIGURATION CORS COMPLÈTE
    # ==========================================================

    CORS(app,
         resources={
             r"/api/*": {
                 "origins": [
                     "http://localhost:5173",
                     "http://127.0.0.1:5173",
                     "http://localhost:3000",
                     "http://127.0.0.1:3000",
                     "http://localhost:5000"
                 ],
                 "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
                 "allow_headers": [
                     "Content-Type",
                     "Authorization",
                     "Access-Control-Allow-Credentials",
                     "Access-Control-Allow-Origin"
                 ],
                 "expose_headers": ["Content-Type", "Authorization"],
                 "supports_credentials": True,
                 "max_age": 3600
             }
         })

    # ==========================================================
    # IMPORT DES MODÈLES
    # ==========================================================

    from app.models import (
        User,
        Niveau,
        Structure,
        Fichier,
        Diffusion,
        Historique,
        Invitation
    )

    # ==========================================================
    # RÉVOCATION DE TOKEN PAR "EPOCH"
    # ==========================================================
    # Chaque JWT embarque la valeur de user.jwt_epoch au moment de sa
    # création (cf. create_access_token(..., additional_claims=...)
    # dans auth_routes.py). Cette valeur est incrémentée en base à
    # chaque désactivation de compte ou changement de mot de passe.
    # Sans ce mécanisme, un token émis avant une désactivation restait
    # valide jusqu'à son expiration naturelle (jusqu'à 8h) : la
    # désactivation n'avait alors aucun effet immédiat.

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        user_id = jwt_payload.get("sub")
        token_epoch = jwt_payload.get("epoch", 0)
        user = db.session.get(User, user_id)
        if not user:
            return True
        return user.jwt_epoch != token_epoch

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "message": "Votre session n'est plus valide (mot de passe changé "
                       "ou compte désactivé). Reconnectez-vous."
        }), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"message": "Votre session a expiré. Reconnectez-vous."}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(reason):
        return jsonify({"message": "Authentification requise."}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(reason):
        return jsonify({"message": "Session invalide. Reconnectez-vous."}), 401

    # ==========================================================
    # IMPORT DES ROUTES (BLUEPRINTS)
    # ==========================================================

    from app.routes.auth_routes import auth_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.file_routes import file_bp
    from app.routes.target_routes import target_bp
    from app.routes.history_routes import history_bp
    from app.routes.niveau_routes import niveau_bp
    from app.routes.structure_routes import structure_bp
    from app.routes.directory_routes import directory_bp

    # ==========================================================
    # ENREGISTREMENT DES BLUEPRINTS
    # ==========================================================

    app.register_blueprint(auth_bp)        # /api/auth/*
    app.register_blueprint(admin_bp)       # /api/admin/*
    app.register_blueprint(file_bp)        # /api/files/*
    app.register_blueprint(target_bp)      # /api/targets/*
    app.register_blueprint(history_bp)     # /api/history/*
    app.register_blueprint(niveau_bp)      # /api/admin/niveaux/*
    app.register_blueprint(structure_bp)   # /api/admin/structures/*
    app.register_blueprint(directory_bp)   # /api/users/*

    # ==========================================================
    # GESTION D'ERREUR : FICHIER TROP VOLUMINEUX
    # ==========================================================

    @app.errorhandler(413)
    def file_too_large(e):
        return jsonify({
            "message": "Le fichier ou la requête dépasse la taille maximale autorisée."
        }), 413

    # ==========================================================
    # CRÉATION DES TABLES EN BASE DE DONNÉES
    # ==========================================================

    with app.app_context():
        db.create_all()
        print("✅ Base de données initialisée avec succès")

    # ==========================================================
    # ROUTE DE TEST
    # ==========================================================

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return {
            "status": "OK",
            "message": "L'API Flask fonctionne correctement"
        }, 200

    return app
