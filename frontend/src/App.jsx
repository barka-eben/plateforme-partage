import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/layout/ProtectedRoute";
import AppLayout from "./components/layout/AppLayout";

import Login from "./pages/Login";
import ActivateAccount from "./pages/ActivateAccount";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import SendFile from "./pages/SendFile";
import History from "./pages/History";
import ChangePassword from "./pages/ChangePassword";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminNiveaux from "./pages/admin/AdminNiveaux";
import AdminStructures from "./pages/admin/AdminStructures";
import AdminJournal from "./pages/admin/AdminJournal";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/connexion" element={<Login />} />
          <Route path="/activer-compte" element={<ActivateAccount />} />
          <Route path="/mot-de-passe-oublie" element={<ForgotPassword />} />

          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/envoyer" element={<SendFile />} />
            <Route path="/historique" element={<History />} />
            <Route path="/mot-de-passe" element={<ChangePassword />} />

            {/* Ouvert à tout utilisateur habilité (admin ou manager) : le
                backend applique la vraie règle hiérarchique (cf. correctif
                "Création déléguée inaccessible"). */}
            <Route path="/admin/utilisateurs" element={<AdminUsers />} />
            <Route
              path="/admin/niveaux"
              element={
                <ProtectedRoute adminOnly>
                  <AdminNiveaux />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/structures"
              element={
                <ProtectedRoute adminOnly>
                  <AdminStructures />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin/journal"
              element={
                <ProtectedRoute adminOnly>
                  <AdminJournal />
                </ProtectedRoute>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
