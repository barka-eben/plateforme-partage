"""
Utilitaires de validation transverses :
  - normalisation des emails (evite les doublons "a@b.com" / "A@B.com")
  - validation grossiere des blobs cryptographiques envoyes par le
    navigateur a l'activation / au changement de mot de passe, pour
    eviter qu'une valeur invalide ne "briquée" silencieusement un
    compte (personne ne pourrait plus jamais lui envoyer de fichier).

Le serveur ne peut PAS valider le contenu cryptographique lui-meme
(il n'a pas la cle privee), mais peut au moins verifier :
  - que c'est du base64 valide,
  - que la taille decodee correspond a l'ordre de grandeur attendu
    pour une cle SPKI RSA-2048 (~294 octets) ou un blob chiffre
    AES-GCM raisonnable.
"""

import base64
import binascii

# SPKI RSA-2048 : ~294 octets. On tolere une marge pour les variations
# d'encodage ASN.1 (attributs optionnels).
RSA_SPKI_MIN_BYTES = 250
RSA_SPKI_MAX_BYTES = 400

# Sel PBKDF2 : 16 octets bruts -> 24 caracteres base64 environ.
SALT_MIN_B64_LEN = 16

# Un blob AES-GCM (iv 12 octets + ciphertext + tag 16 octets) pour DEUX
# clés privées RSA-2048 (PKCS8, ~1218 octets chacune) encodées en JSON
# base64 fait plusieurs kilo-octets. On se contente d'un plancher bas
# pour repousser les valeurs manifestement absurdes ("BBBB", "" ...)
# sans être trop strict sur le format JSON interne exact.
PRIVATE_BUNDLE_MIN_B64_LEN = 200


def normalize_email(email):
    if not email:
        return email
    return email.strip().lower()


def _b64_decoded_len(value):
    try:
        return len(base64.b64decode(value, validate=False))
    except (binascii.Error, ValueError, TypeError):
        return None


def is_valid_public_key_b64(value):
    if not value or not isinstance(value, str):
        return False
    n = _b64_decoded_len(value)
    if n is None:
        return False
    return RSA_SPKI_MIN_BYTES <= n <= RSA_SPKI_MAX_BYTES


def is_valid_salt_b64(value):
    if not value or not isinstance(value, str):
        return False
    n = _b64_decoded_len(value)
    if n is None:
        return False
    return n >= SALT_MIN_B64_LEN


def is_valid_private_bundle_b64(value):
    if not value or not isinstance(value, str):
        return False
    if len(value) < PRIVATE_BUNDLE_MIN_B64_LEN:
        return False
    n = _b64_decoded_len(value)
    return n is not None
