# backend/app/services/email_service.py
"""
Service d'envoi d'email d'invitation.

En developpement (pas de SMTP_HOST configure), le lien est simplement
affiche dans les logs du serveur Flask pour pouvoir tester tout le
parcours sans dependance externe. En production, renseigner les
variables SMTP_* dans .env pour un envoi reel.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@plateforme-securisee.local")


def build_activation_link(email, token):
    from urllib.parse import quote
    return f"{FRONTEND_URL}/activer-compte?email={quote(email)}&token={quote(token)}"


def send_security_notification(email, nom, prenom, sujet_court, corps_evenement):
    """
    Notifie le titulaire d'un compte d'un evenement de securite
    (changement de mot de passe, utilisation du code de recuperation,
    desactivation du compte...). Purement informatif : ne bloque
    jamais l'action meme en cas d'echec d'envoi.
    """
    subject = f"[Sécurité] {sujet_court} - Plateforme sécurisée"
    body = f"""Bonjour {prenom} {nom},

{corps_evenement}

Si vous n'êtes pas à l'origine de cette action, contactez immédiatement
votre administrateur système.

Cordialement,
L'équipe administrative"""

    if not SMTP_HOST:
        print("=" * 70)
        print("[EMAIL SIMULE - notification de sécurité]")
        print(f"A : {email}")
        print(f"Sujet : {subject}")
        print(body)
        print("=" * 70)
        return

    try:
        message = MIMEMultipart()
        message["From"] = SMTP_FROM
        message["To"] = email
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [email], message.as_string())
    except Exception as exc:
        print(f"[EMAIL] Echec de la notification de sécurité a {email} : {exc}")


def send_invitation_email(email, nom, prenom, token):
    """
    Envoie (ou simule) l'email d'invitation avec le lien d'activation.
    Retourne toujours le lien genere, pour permettre a la route
    appelante de le renvoyer en reponse en mode developpement.
    """

    activation_link = build_activation_link(email, token)

    subject = "Activation de votre compte - Plateforme sécurisée"
    body = f"""Bonjour {prenom} {nom},

Un compte a ete cree pour vous sur la Plateforme de partage securise
de documents administratifs.

Veuillez cliquer sur le lien ci-dessous pour choisir votre mot de
passe et activer votre compte :

{activation_link}

Ce lien est valable 24 heures et ne peut etre utilise qu'une seule fois.

Cordialement,
L'equipe administrative"""

    if not SMTP_HOST:
        # Mode developpement : pas de serveur SMTP configure.
        print("=" * 70)
        print("[EMAIL SIMULE - configurer SMTP_HOST dans .env pour un envoi reel]")
        print(f"A : {email}")
        print(f"Sujet : {subject}")
        print(body)
        print("=" * 70)
        return activation_link

    try:
        message = MIMEMultipart()
        message["From"] = SMTP_FROM
        message["To"] = email
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [email], message.as_string())

    except Exception as exc:
        # On ne bloque jamais la creation de compte a cause d'un
        # probleme d'envoi d'email : on journalise et on continue.
        # L'administrateur pourra toujours renvoyer l'invitation.
        print(f"[EMAIL] Echec de l'envoi a {email} : {exc}")

    return activation_link
