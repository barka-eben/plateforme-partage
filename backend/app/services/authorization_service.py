from app import db
from sqlalchemy import text


def get_descendant_structure_ids(structure_id):
    """
    Retourne l'identifiant de la structure donnée
    ainsi que tous ses descendants.
    """

    query = text("""
        WITH RECURSIVE structure_tree AS (

            -- 1. Structure de départ
            SELECT id
            FROM structures
            WHERE id = :structure_id

            UNION ALL

            -- 2. Récupérer les structures enfants
            SELECT s.id
            FROM structures s
            INNER JOIN structure_tree st
                ON s.structure_parent_id = st.id
        )

        SELECT id
        FROM structure_tree;
    """)

    result = db.session.execute(
        query,
        {"structure_id": structure_id}
    )

    return [row[0] for row in result]


def get_ancestor_structure_ids(structure_id):
    """
    Retourne l'identifiant de la structure donnee ainsi que tous ses
    ancetres (utile pour verifier si une structure B est "sous"
    une structure A sans devoir remonter tout l'arbre en Python).
    """

    query = text("""
        WITH RECURSIVE structure_ancestors AS (

            SELECT id, structure_parent_id
            FROM structures
            WHERE id = :structure_id

            UNION ALL

            SELECT s.id, s.structure_parent_id
            FROM structures s
            INNER JOIN structure_ancestors sa
                ON s.id = sa.structure_parent_id
        )

        SELECT id
        FROM structure_ancestors;
    """)

    result = db.session.execute(
        query,
        {"structure_id": structure_id}
    )

    return [row[0] for row in result]


def structure_has_users_or_children(structure_id):
    """
    Empeche la suppression d'une structure qui contient encore des
    utilisateurs ou des sous-structures (integrite metier minimale).
    """

    from app.models import User, Structure

    has_users = db.session.query(
        User.query.filter_by(structure_id=structure_id).exists()
    ).scalar()

    has_children = db.session.query(
        Structure.query.filter_by(structure_parent_id=structure_id).exists()
    ).scalar()

    return bool(has_users or has_children)