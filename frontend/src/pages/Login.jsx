import { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Alert from "../components/common/Alert";
import Button from "../components/common/Button";

export default function Login() {
  const { login, accountNeedsActivation, sessionMessage, clearSessionMessage } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Correctif : un 401 de session (token expiré/révoqué) est
  // maintenant signalé ici, plutôt que de laisser l'utilisateur sur
  // une page qui ne répond plus (cf. api.js / AuthContext.jsx).
  useEffect(() => {
    if (sessionMessage) {
      setError(sessionMessage);
      clearSessionMessage();
    }
  }, [sessionMessage, clearSessionMessage]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      const needsActivation = result?.needsActivation ?? accountNeedsActivation;
      const dest = needsActivation ? "/activer-compte" : location.state?.from?.pathname || "/";
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message || "Échec de la connexion");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-white">Partage Sécurisé</h1>
          <p className="mt-1 text-sm text-brand-300">
            Plateforme de diffusion de documents administratifs
          </p>
        </div>

        <form onSubmit={handleSubmit} className="rounded-2xl bg-white p-6 shadow-xl">
          <h2 className="mb-4 text-lg font-semibold text-slate-800">Connexion</h2>

          {error && <Alert type="error" className="mb-4">{error}</Alert>}

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder="prenom.nom@administration.gov"
            />
          </div>

          <div className="mb-2">
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Mot de passe
            </label>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              placeholder="••••••••"
            />
          </div>

          <p className="mb-6 text-right text-xs">
            <Link to="/mot-de-passe-oublie" className="text-brand-600 hover:underline">
              Mot de passe oublié ?
            </Link>
          </p>

          <Button type="submit" loading={loading} className="w-full">
            Se connecter
          </Button>

          <p className="mt-4 text-center text-xs text-slate-400">
            Reçu un lien d'invitation ?{" "}
            <Link to="/activer-compte" className="text-brand-600 hover:underline">
              Activer mon compte
            </Link>
          </p>
        </form>

        <p className="mt-6 text-center text-xs text-brand-400">
          Votre clé privée est déchiffrée localement, dans votre navigateur, à partir de
          votre mot de passe. Elle n'est jamais transmise au serveur.
        </p>
      </div>
    </div>
  );
}
