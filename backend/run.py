from app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    # Hôte et debug lus depuis l'environnement, avec des DÉFAUTS SÛRS.
    # Auparavant : host="0.0.0.0" et debug=True codés en dur, ce qui
    # exposait le débogueur Werkzeug (exécution de code arbitraire) au
    # réseau local dès que la machine de dev était accessible.
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"

    if debug and host != "127.0.0.1":
        print(
            "⚠️  ATTENTION : FLASK_DEBUG=1 avec un hôte réseau "
            f"({host}) expose le débogueur Werkzeug. À ne JAMAIS faire "
            "en dehors d'un poste de développement isolé."
        )

    app.run(host=host, port=port, debug=debug)
