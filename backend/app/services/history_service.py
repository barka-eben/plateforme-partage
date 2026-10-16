import uuid

from flask import request

from app import db
from app.models import Historique


def _client_ip():
    # X-Forwarded-For : utile derriere un reverse proxy (nginx, etc.).
    # On ne garde que la premiere adresse de la liste (celle du client
    # d'origine) ; les suivantes peuvent avoir ete ajoutees par des
    # proxys intermediaires non necessairement fiables.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def log_action(utilisateur_id, action, statut_action, fichier_id=None,
                cible_utilisateur_id=None, detail=None):
    """
    Cree une entree dans la table Historique.

    N'appelle PAS db.session.commit() : l'appelant est responsable du
    commit (souvent groupe avec d'autres ecritures dans la meme
    transaction).

    cible_utilisateur_id : a renseigner pour toute action effectuee
    PAR un utilisateur SUR un autre compte (creation, modification,
    activation, desactivation, renvoi d'invitation...), pour que le
    journal reste exploitable en audit.
    """
    try:
        ip = _client_ip()
    except RuntimeError:
        # log_action peut etre appele hors contexte de requete HTTP
        # (scripts d'administration) : pas d'IP dans ce cas.
        ip = None

    entree = Historique(
        id=f"HIST-{uuid.uuid4()}",
        action=action,
        statut_action=statut_action,
        utilisateur_id=utilisateur_id,
        fichier_id=fichier_id,
        cible_utilisateur_id=cible_utilisateur_id,
        ip_adresse=ip,
        detail=detail
    )

    db.session.add(entree)
    return entree
