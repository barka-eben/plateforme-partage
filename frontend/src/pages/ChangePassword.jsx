import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { estimatePasswordStrength } from "../crypto/cryptoService";
import { Card, CardHeader } from "../components/common/Card";
import Input from "../components/common/Input";
import Button from "../components/common/Button";
import Alert from "../components/common/Alert";

export default function ChangePassword() {
  const { changePassword } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const strength = estimatePasswordStrength(newPassword);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess(false);

    if (newPassword.length < 10 || newPassword.length > 72 ||
        !/[a-zA-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError(
        "Le nouveau mot de passe doit contenir entre 10 et 72 caractères, " +
          "avec au moins une lettre et un chiffre."
      );
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }

    setLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-1 text-xl font-bold text-slate-900">Changer mon mot de passe</h1>
      <p className="mb-6 text-sm text-slate-500">
        Votre clé privée est re-chiffrée localement avec le nouveau mot de passe ; elle
        n'est jamais envoyée en clair au serveur.
      </p>

      <Card>
        <CardHeader title="Nouveau mot de passe" />
        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-5">
          {success && (
            <Alert type="success">Mot de passe modifié avec succès.</Alert>
          )}
          {error && <Alert type="error">{error}</Alert>}

          <Input
            label="Mot de passe actuel"
            type="password"
            required
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />

          <div>
            <Input
              label="Nouveau mot de passe"
              type="password"
              required
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            {newPassword && (
              <p className="mt-1 text-xs text-slate-500">
                Robustesse : {strength.label} · 10-72 caractères, au moins une lettre et un chiffre
              </p>
            )}
          </div>

          <Input
            label="Confirmer le nouveau mot de passe"
            type="password"
            required
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />

          <Alert type="warning">
            Vos clés de chiffrement existantes seront re-protégées avec ce nouveau
            mot de passe (vos fichiers déjà reçus restent lisibles), et vos autres
            sessions ouvertes seront déconnectées.
          </Alert>

          <Button type="submit" loading={loading} className="w-full">
            Mettre à jour le mot de passe
          </Button>
        </form>
      </Card>
    </div>
  );
}
