import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.getenv("JWT_SECRET")

    # Duree de vie du token JWT. Le mot de passe n'est jamais renvoye
    # au serveur apres le login, donc un token expire oblige juste a
    # se reconnecter (et a redechiffrer la cle privee cote navigateur)
    # - pas de perte de donnees.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.getenv("JWT_EXPIRES_HOURS", "8"))
    )

    # Taille maximale d'une requete (upload de fichier inclus). Sans
    # cette limite, seule la limite cote navigateur (50 Mo, dans
    # SendFile.jsx) protegeait le serveur : un client different du
    # frontend officiel pouvait envoyer un fichier arbitrairement gros.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "60")) * 1024 * 1024

    # Active/desactive la limitation de debit (flask-limiter). A
    # laisser active en production ; peut etre desactivee dans des
    # tests unitaires qui font volontairement de nombreuses requetes.
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "1") == "1"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
