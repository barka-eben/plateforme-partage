import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isCryptoUnlocked, accountNeedsActivation, user } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/connexion" state={{ from: location }} replace />;
  }

  // Correctif : l'admin passait auparavant par un compte "bootstrap"
  // créé directement ACTIF, sans jamais activer ni générer de clés.
  // Il est désormais provisionné par invitation comme tout le monde
  // (cf. scripts/init_db.py) : il doit donc, lui aussi, activer son
  // compte et avoir ses clés déchiffrées pour accéder à l'application.
  if (accountNeedsActivation) {
    return <Navigate to="/activer-compte" state={{ from: location }} replace />;
  }

  if (!isCryptoUnlocked) {
    return <Navigate to="/connexion" state={{ from: location }} replace />;
  }

  if (adminOnly && !user.est_administrateur_systeme) {
    return <Navigate to="/" replace />;
  }

  return children;
}
