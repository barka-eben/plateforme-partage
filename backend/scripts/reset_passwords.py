# backend/scripts/reset_passwords.py
"""
Cet ancien script réinitialisait un mot de passe en base SANS jamais
toucher aux clés RSA associées : le compte redevenait connectable,
mais sa clé privée chiffrée restait dérivée de l'ANCIEN mot de passe,
donc indéchiffrable avec le nouveau. Résultat : un compte "réparé"
qui ne pouvait plus lire aucun fichier déjà reçu, ni en envoyer, sans
que rien ne le signale à l'utilisateur. Il a été supprimé pour ne
plus pouvoir être exécuté par erreur.

Pour un compte qui a perdu son mot de passe, deux chemins existent
désormais, correctement intégrés à la cryptographie de bout en bout :

1. Le TITULAIRE du compte utilise son CODE DE RÉCUPÉRATION (affiché
   une seule fois à l'activation) sur la page "Mot de passe oublié"
   du frontend (/mot-de-passe-oublie). C'est le chemin normal : les
   clés sont re-chiffrées côté navigateur, aucune perte de données.

2. Si le code de récupération est également perdu, il n'existe
   AUCUN moyen de récupérer les fichiers déjà chiffrés pour ce compte
   (c'est la garantie du chiffrement de bout en bout : ni la base de
   données ni un administrateur ne peuvent déchiffrer une clé privée
   sans le mot de passe ou le code de récupération). Un administrateur
   peut seulement :
     - désactiver le compte compromis/perdu (POST /admin/users/<id>/deactivate) ;
     - provisionner un nouveau compte pour la même personne, qui
       recevra les fichiers futurs sous une nouvelle identité
       cryptographique (les fichiers déjà envoyés à l'ancien compte
       resteront définitivement illisibles).

Voir README.md, section "Récupération de compte", pour le détail.
"""

if __name__ == "__main__":
    print(__doc__)
