"""
Génère de fausses valeurs cryptographiques PLAUSIBLES (bonne taille,
bon encodage base64) pour tester la logique métier du backend sans
dépendre d'un vrai moteur RSA/AES (qui vit côté navigateur, en JS).

Ces tests ne vérifient donc PAS la correction cryptographique du
protocole (couverte par les tests end-to-end JS, cf. README section
"Tests"), seulement le comportement de l'API : statuts HTTP, règles
d'autorisation, validations de format, cycle de vie des comptes.
"""
import base64
import hashlib
import os


def fake_public_key_b64():
    return base64.b64encode(os.urandom(294)).decode()


def fake_salt_b64():
    return base64.b64encode(os.urandom(16)).decode()


def fake_private_bundle_b64():
    return base64.b64encode(os.urandom(600)).decode()


def fake_recovery_code():
    return "ABCDE-FGHJK-MNPQR-STUVW-XYZ23"


def fake_recovery_code_hash(code=None):
    code = code or fake_recovery_code()
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def activation_payload(email, token, password="MotDePasse123"):
    return {
        "email": email,
        "token": token,
        "password": password,
        "publicKey": fake_public_key_b64(),
        "publicKeySignature": fake_public_key_b64(),
        "encryptedPrivateKey": fake_private_bundle_b64(),
        "salt": fake_salt_b64(),
        "recoveryEncryptedPrivateKey": fake_private_bundle_b64(),
        "recoverySalt": fake_salt_b64(),
        "recoveryCodeHash": fake_recovery_code_hash(),
    }
