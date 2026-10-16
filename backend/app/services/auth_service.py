import secrets
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt


# Duree de validite d'un lien d'invitation (cf. cahier des charges : 24h)
INVITATION_VALIDITY_HOURS = 24

# Politique de robustesse du mot de passe, verifiee cote serveur en
# complement du controle (recommande) cote client.
PASSWORD_MIN_LENGTH = 10

# bcrypt tronque silencieusement au-dela de 72 OCTETS (pas caracteres)
# et leve une ValueError au-dela sur les versions recentes (>=4.1).
# On refuse proprement plutot que de laisser un mot de passe long
# faire planter l'activation ou le login avec une erreur 500.
PASSWORD_MAX_BYTES = 72

# Recommandation OWASP (2023+) pour PBKDF2-HMAC-SHA256. Historiquement
# ce projet utilisait 210 000 (qui est la recommandation pour SHA-512,
# pas SHA-256) : la valeur correcte pour SHA-256 est 600 000.
PBKDF2_ITERATIONS = 600_000

# Longueur (en octets, avant encodage base64) d'un code de recuperation
# genere cote navigateur. 20 octets = ~160 bits d'entropie : largement
# suffisant pour resister a une attaque hors-ligne meme sans limitation
# de debit, puisqu'aucun hachage lent ne protege ce code cote serveur
# (seule son empreinte SHA-256 y est stockee, pour verification rapide).
RECOVERY_CODE_BYTES = 20


def _password_too_long(password):
    return len(password.encode("utf-8")) > PASSWORD_MAX_BYTES


def hash_password(password):
    """
    Hache un mot de passe avec bcrypt.

    Leve ValueError si le mot de passe depasse PASSWORD_MAX_BYTES
    (au lieu de laisser bcrypt lever une exception non geree) : les
    appelants DOIVENT valider avec is_password_strong_enough() avant
    d'appeler cette fonction.
    """
    if _password_too_long(password):
        raise ValueError(
            f"Le mot de passe ne doit pas depasser {PASSWORD_MAX_BYTES} octets"
        )

    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password, password_hash):
    if not password_hash or not password:
        return False

    if _password_too_long(password):
        # Un mot de passe trop long ne peut de toute facon pas
        # correspondre a un hash valide : on renvoie simplement
        # "faux" plutot que de laisser bcrypt lever une exception.
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def is_password_strong_enough(password):
    """
    Verification minimale et deliberement simple cote serveur. Le gros
    du controle (entropie, dictionnaire...) doit se faire cote React
    pour un retour immediat ; le serveur ne fait ici qu'une derniere
    barriere de securite, IDENTIQUE a celle du navigateur (meme regle
    des deux cotes, pour eviter la confusion "accepte cote client puis
    rejete cote serveur").
    """
    if not password:
        return False

    if len(password) < PASSWORD_MIN_LENGTH:
        return False

    if _password_too_long(password):
        return False

    has_digit = any(c.isdigit() for c in password)
    has_alpha = any(c.isalpha() for c in password)

    return has_digit and has_alpha


def generate_invitation_token():
    """
    Genere un token d'invitation a usage unique.

    Retourne (token_en_clair, token_hash) : le premier part dans le
    lien envoye par email, jamais stocke tel quel ; le second (sha256)
    est persiste en base.
    """
    token_en_clair = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_en_clair.encode("utf-8")).hexdigest()
    return token_en_clair, token_hash


def hash_invitation_token(token_en_clair):
    return hashlib.sha256(token_en_clair.encode("utf-8")).hexdigest()


def invitation_expiration():
    return datetime.now(timezone.utc) + timedelta(hours=INVITATION_VALIDITY_HOURS)


def is_invitation_expired(date_expiration):
    now = datetime.now(timezone.utc)
    if date_expiration.tzinfo is None:
        date_expiration = date_expiration.replace(tzinfo=timezone.utc)
    return now > date_expiration


def generate_recovery_code():
    """
    Genere un code de recuperation lisible par un humain (pour le
    recopier / le noter), a haute entropie. Format : groupes de 5
    caracteres alphanumeriques (alphabet reduit, sans caracteres
    ambigus 0/O/1/I/L), separes par des tirets.
    """
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    raw = secrets.token_bytes(RECOVERY_CODE_BYTES)
    # Convertit les octets aleatoires en une chaine sur cet alphabet.
    chars = []
    acc = int.from_bytes(raw, "big")
    base = len(alphabet)
    length = 26  # suffisant pour epuiser l'entropie de 20 octets
    for _ in range(length):
        acc, rem = divmod(acc, base)
        chars.append(alphabet[rem])
    code = "".join(chars)
    groups = [code[i:i + 5] for i in range(0, len(code), 5)]
    return "-".join(groups)


def hash_recovery_code(code):
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
