# backend/scripts/clean_db.py
"""
Script pour nettoyer la base de données.
Attention : supprime TOUTES les données !
"""

import sys
import os

# Ajouter le dossier parent (backend) au PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Niveau, Structure, Fichier, Diffusion, Historique


def clean_database():
    """Supprime toutes les données de la base."""
    
    app = create_app()
    
    with app.app_context():
        
        print("=" * 50)
        print("⚠️  NETTOYAGE DE LA BASE DE DONNÉES")
        print("=" * 50)
        
        confirmation = input("\n⚠️  Êtes-vous sûr de vouloir supprimer toutes les données ? (oui/non) : ")
        
        if confirmation.lower() != "oui":
            print("❌ Opération annulée.")
            return
        
        print("\n🗑️  Suppression des données...")
        
        # Supprimer dans l'ordre inverse des dépendances
        print("  Suppression de l'historique...")
        db.session.query(Historique).delete()
        
        print("  Suppression des diffusions...")
        db.session.query(Diffusion).delete()
        
        print("  Suppression des fichiers...")
        db.session.query(Fichier).delete()
        
        print("  Suppression des utilisateurs...")
        db.session.query(User).delete()
        
        print("  Suppression des structures...")
        db.session.query(Structure).delete()
        
        print("  Suppression des niveaux...")
        db.session.query(Niveau).delete()
        
        db.session.commit()
        
        print("\n✅ Toutes les données ont été supprimées !")
        print("ℹ️  Les tables existent toujours mais sont vides.")
        print("ℹ️  Pour recréer les données, exécutez : python -m scripts.init_db")


if __name__ == "__main__":
    clean_database()