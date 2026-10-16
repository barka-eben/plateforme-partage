import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const linkClasses = ({ isActive }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-brand-800 text-white"
      : "text-brand-100 hover:bg-brand-800/60 hover:text-white"
  }`;

function Icon({ path }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const ICONS = {
  dashboard: "M4 4h6v6H4V4zm10 0h6v6h-6V4zM4 14h6v6H4v-6zm10 0h6v6h-6v-6z",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z",
  history: "M3 3v5h5M3.05 13A9 9 0 106 5.3L3 8m9-1v5l3 3",
  users: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
  levels: "M3 6h18M3 12h12M3 18h6",
  org: "M12 2v6m0 0L6 12m6-4l6 4M4 12v6m0 0h4m-4 0H4m16-6v6m0 0h-4m4 0h4",
  journal: "M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z",
  lock: "M19 11H5a2 2 0 00-2 2v7a2 2 0 002 2h14a2 2 0 002-2v-7a2 2 0 00-2-2zM7 11V7a5 5 0 0110 0v4",
  logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9",
};

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/connexion", { replace: true });
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="flex w-64 shrink-0 flex-col bg-brand-950 px-4 py-6">
        <div className="mb-8 px-2">
          <p className="text-lg font-bold text-white leading-tight">Partage Sécurisé</p>
          <p className="text-xs text-brand-300">Plateforme administrative</p>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          <NavLink to="/" end className={linkClasses}>
            <Icon path={ICONS.dashboard} /> Tableau de bord
          </NavLink>
          <NavLink to="/envoyer" className={linkClasses}>
            <Icon path={ICONS.send} /> Envoyer un fichier
          </NavLink>
          <NavLink to="/historique" className={linkClasses}>
            <Icon path={ICONS.history} /> Mon historique
          </NavLink>

          {/* "Comptes" est ouvert à tout utilisateur habilité à gérer des
              subordonnés (le backend applique la règle hiérarchique réelle,
              cf. admin_routes.py) — pas seulement à l'administrateur système.
              Correctif : cette page était auparavant réservée à l'admin,
              alors même que l'API autorisait déjà les managers à créer des
              comptes de niveau inférieur dans leur structure. */}
          <NavLink to="/admin/utilisateurs" className={linkClasses}>
            <Icon path={ICONS.users} /> Comptes
          </NavLink>

          {user?.est_administrateur_systeme && (
            <>
              <div className="mt-5 mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-brand-400">
                Administration système
              </div>
              <NavLink to="/admin/niveaux" className={linkClasses}>
                <Icon path={ICONS.levels} /> Niveaux
              </NavLink>
              <NavLink to="/admin/structures" className={linkClasses}>
                <Icon path={ICONS.org} /> Organigramme
              </NavLink>
              <NavLink to="/admin/journal" className={linkClasses}>
                <Icon path={ICONS.journal} /> Journal global
              </NavLink>
            </>
          )}

          <NavLink to="/mot-de-passe" className={linkClasses}>
            <Icon path={ICONS.lock} /> Changer mon mot de passe
          </NavLink>
        </nav>

        <div className="mt-4 border-t border-brand-800 pt-4">
          <div className="mb-3 px-2">
            <p className="truncate text-sm font-medium text-white">
              {user?.prenom} {user?.nom}
            </p>
            <p className="truncate text-xs text-brand-300">{user?.poste_administratif}</p>
          </div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-brand-100 hover:bg-brand-800/60 hover:text-white"
          >
            <Icon path={ICONS.logout} /> Déconnexion
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
