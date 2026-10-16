import { useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { api } from "../services/api";
import {
  deriveKeyFromRecoveryCode,
  decryptPrivateBundle,
  encryptPrivateBundle,
  generateSaltBase64,
  deriveKeyFromPassword,
  generateRecoveryCode,
  hashRecoveryCode,
  estimatePasswordStrength,
} from "../crypto/cryptoService";
import { Card, CardHeader } from "../components/common/Card";
import Input from "../components/common/Input";
import Button from "../components/common/Button";
import Alert from "../components/common/Alert";

const STEPS = {
  VERIFY: "verify",
  NEW_PASSWORD: "new_password",
  DONE: "done",
};

/**
 * Page "Mot de passe oublié".
 *
 * Étape 1 : l'utilisateur saisit son email + son code de récupération
 * (affiché une seule fois à l'activation, cf. ActivateAccount.jsx).
 * Le serveur vérifie l'empreinte du code et renvoie le bundle de clés
 * privées chiffré POUR la récupération.
 *
 * Étape 2 : le navigateur déchiffre ce bundle localement avec une clé
 * dérivée du code, puis le re-chiffre avec le NOUVEAU mot de passe.
 * Un NOUVEAU code de récupération est aussi généré (l'ancien est à
 * usage unique) et affiché une seule fois.
 *
 * À aucun moment le serveur ne voit une clé privée en clair, ni le
 * mot de passe sous une autre forme que son hash bcrypt final.
 */
export default function ForgotPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [step, setStep] = useState(STEPS.VERIFY);
  const [email, setEmail] = useState(searchParams.get("email") || "");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [recoveredBundle, setRecoveredBundle] = useState(null); // { oaepPrivateKeyRaw, pssPrivateKeyRaw }
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [newRecoveryCode, setNewRecoveryCode] = useState(null);
  const [codeSaved, setCodeSaved] = useState(false);

  const strength = estimatePasswordStrength(newPassword);

  const handleVerify = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api.post("/auth/forgot-password/verify", {
        email: email.trim().toLowerCase(),
        recoveryCode: recoveryCode.trim(),
      });

      const key = await deriveKeyFromRecoveryCode(recoveryCode, data.sel_recovery);
      const bundle = await decryptPrivateBundle(data.cle_privee_chiffree_recovery, key);

      setRecoveredBundle(bundle);
      setStep(STEPS.NEW_PASSWORD);
    } catch (err) {
      setError(
        err.message ||
          "Impossible de déchiffrer vos clés avec ce code : vérifiez l'email et le code saisis."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 10 || newPassword.length > 72 ||
        !/[a-zA-Z]/.test(newPassword) || !/\d/.test(newPassword)) {
      setError("Le mot de passe doit contenir entre 10 et 72 caractères, avec au moins une lettre et un chiffre.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }

    setLoading(true);
    try {
      const newSalt = generateSaltBase64();
      const newKey = await deriveKeyFromPassword(newPassword, newSalt);
      const newEncryptedPrivateKey = await encryptPrivateBundle(
        recoveredBundle.oaepPrivateKeyRaw, recoveredBundle.pssPrivateKeyRaw, newKey
      );

      // L'ancien code de récupération est à usage unique : on en
      // génère systématiquement un nouveau à afficher.
      const freshCode = generateRecoveryCode();
      const freshRecoverySalt = generateSaltBase64();
      const freshRecoveryKey = await deriveKeyFromRecoveryCode(freshCode, freshRecoverySalt);
      const freshRecoveryEncryptedPrivateKey = await encryptPrivateBundle(
        recoveredBundle.oaepPrivateKeyRaw, recoveredBundle.pssPrivateKeyRaw, freshRecoveryKey
      );
      const freshRecoveryCodeHash = await hashRecoveryCode(freshCode);

      await api.post("/auth/forgot-password/reset", {
        email: email.trim().toLowerCase(),
        recoveryCode: recoveryCode.trim(),
        newPassword,
        encryptedPrivateKey: newEncryptedPrivateKey,
        salt: newSalt,
        recoveryEncryptedPrivateKey: freshRecoveryEncryptedPrivateKey,
        recoverySalt: freshRecoverySalt,
        recoveryCodeHash: freshRecoveryCodeHash,
      });

      setNewRecoveryCode(freshCode);
      setStep(STEPS.DONE);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-white">Mot de passe oublié</h1>
        </div>

        <Card>
          {step === STEPS.VERIFY && (
            <>
              <CardHeader title="Étape 1 · Votre code de récupération" />
              <form onSubmit={handleVerify} className="space-y-4 px-5 py-5">
                <Alert type="warning">
                  Ce code vous a été montré UNE SEULE FOIS lors de l'activation de
                  votre compte. Sans lui, il n'existe aucun moyen de récupérer vos
                  fichiers déjà chiffrés : c'est une garantie du chiffrement de
                  bout en bout, pas un oubli.
                </Alert>

                {error && <Alert type="error">{error}</Alert>}

                <Input
                  label="Email"
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />

                <Input
                  label="Code de récupération"
                  type="text"
                  required
                  placeholder="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value)}
                />

                <Button type="submit" loading={loading} className="w-full">
                  Vérifier
                </Button>

                <Link to="/connexion" className="block text-center text-sm text-brand-600 hover:underline">
                  Retour à la connexion
                </Link>
              </form>
            </>
          )}

          {step === STEPS.NEW_PASSWORD && (
            <>
              <CardHeader title="Étape 2 · Nouveau mot de passe" />
              <form onSubmit={handleReset} className="space-y-4 px-5 py-5">
                {error && <Alert type="error">{error}</Alert>}

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
                      Robustesse : {strength.label} · 10-72 caractères, une lettre et un chiffre
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

                <Button type="submit" loading={loading} className="w-full">
                  Réinitialiser le mot de passe
                </Button>
              </form>
            </>
          )}

          {step === STEPS.DONE && (
            <div className="px-5 py-5">
              <Alert type="success" className="mb-4">
                Mot de passe réinitialisé avec succès.
              </Alert>

              <p className="mb-2 text-sm font-semibold text-slate-800">
                Votre nouveau code de récupération
              </p>
              <p className="mb-3 text-sm text-slate-600">
                L'ancien code vient d'être invalidé. Notez celui-ci en lieu sûr : il
                ne sera plus jamais affiché.
              </p>

              <div className="mb-4 rounded-lg border border-slate-300 bg-slate-50 p-3 text-center font-mono text-base tracking-wide text-slate-900">
                {newRecoveryCode}
              </div>

              <label className="mb-4 flex items-start gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={codeSaved}
                  onChange={(e) => setCodeSaved(e.target.checked)}
                  className="mt-1"
                />
                J'ai noté mon nouveau code de récupération en lieu sûr.
              </label>

              <Button type="button" className="w-full" disabled={!codeSaved} onClick={() => navigate("/connexion")}>
                Aller à la connexion
              </Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
