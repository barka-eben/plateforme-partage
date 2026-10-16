import { useState, useEffect } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";
import Alert from "../components/common/Alert";
import Button from "../components/common/Button";
import Spinner from "../components/common/Spinner";
import {
  generateKeyPairsRaw,
  generateSaltBase64,
  deriveKeyFromPassword,
  encryptPrivateBundle,
  bytesToBase64,
  estimatePasswordStrength,
  generateRecoveryCode,
  deriveKeyFromRecoveryCode,
  hashRecoveryCode,
} from "../crypto/cryptoService";

const STRENGTH_COLORS = ["bg-red-500", "bg-red-400", "bg-amber-400", "bg-emerald-400", "bg-emerald-500", "bg-emerald-600"];

// Identiques à PASSWORD_MIN_LENGTH / PASSWORD_MAX_BYTES côté serveur
// (backend/app/services/auth_service.py) : afficher une règle
// différente de celle réellement appliquée ne fait que confondre
// l'utilisateur (correctif : la version précédente n'imposait que
// 10 caractères côté client, sans vérifier lettre+chiffre, alors que
// le serveur exigeait les deux et rejetait ensuite silencieusement).
const PASSWORD_MIN_LENGTH = 10;
const PASSWORD_MAX_LENGTH = 72;

function isPasswordAcceptable(password) {
  if (password.length < PASSWORD_MIN_LENGTH || password.length > PASSWORD_MAX_LENGTH) return false;
  return /[a-zA-Z]/.test(password) && /\d/.test(password);
}

export default function ActivateAccount() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const email = searchParams.get("email") || "";
  const token = searchParams.get("token") || "";

  const [checking, setChecking] = useState(true);
  const [invitationValid, setInvitationValid] = useState(false);
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [manualEmail, setManualEmail] = useState("");
  const [manualToken, setManualToken] = useState("");
  const [manualMode, setManualMode] = useState(!email || !token);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState(null);
  const [recoveryCodeSaved, setRecoveryCodeSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  const strength = estimatePasswordStrength(password);
  const secureContext = typeof window !== "undefined" ? window.isSecureContext : true;

  async function verifyInvitation(currentEmail, currentToken) {
    if (!currentEmail || !currentToken) {
      setError("Lien d'invitation incomplet. Vérifiez l'URL reçue par email.");
      setChecking(false);
      setManualMode(true);
      return;
    }

    try {
      const data = await api.post("/auth/verify-invitation", {
        email: currentEmail,
        token: currentToken,
      });
      setInvite(data);
      setInvitationValid(true);
      setManualMode(false);
    } catch (err) {
      setError(err.message);
      setManualMode(true);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    if (!email || !token) {
      setManualMode(true);
      setChecking(false);
      setError("Lien d'invitation incomplet. Vérifiez l'URL reçue par email.");
      return;
    }

    verifyInvitation(email, token);
  }, [email, token]);

  const handleManualSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setChecking(true);
    await verifyInvitation(manualEmail.trim(), manualToken.trim());
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!secureContext) {
      setError(
        "Ce navigateur ne considère pas cette page comme sécurisée (HTTPS ou " +
          "localhost requis) : les fonctions de chiffrement ne sont pas disponibles."
      );
      return;
    }

    if (!isPasswordAcceptable(password)) {
      setError(
        `Le mot de passe doit contenir entre ${PASSWORD_MIN_LENGTH} et ` +
          `${PASSWORD_MAX_LENGTH} caractères, avec au moins une lettre et un chiffre.`
      );
      return;
    }
    if (password !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }

    setSubmitting(true);
    try {
      // 1. Génération LOCALE de deux paires de clés RSA-2048 : une
      // pour chiffrer (OAEP), une pour signer (PSS). Ne jamais
      // réutiliser la même paire pour les deux usages.
      const { oaep, pss } = await generateKeyPairsRaw();

      // 2. Dérivation d'une clé depuis le mot de passe choisi.
      const salt = generateSaltBase64();
      const derivedKey = await deriveKeyFromPassword(password, salt);
      const encryptedPrivateKey = await encryptPrivateBundle(
        oaep.privateKeyRaw, pss.privateKeyRaw, derivedKey
      );

      // 3. Génération d'un CODE DE RÉCUPÉRATION affiché une seule
      // fois : permet de réinitialiser le mot de passe plus tard sans
      // perdre l'accès aux fichiers déjà reçus (cf. ForgotPassword.jsx).
      const code = generateRecoveryCode();
      const recoverySalt = generateSaltBase64();
      const recoveryKey = await deriveKeyFromRecoveryCode(code, recoverySalt);
      const recoveryEncryptedPrivateKey = await encryptPrivateBundle(
        oaep.privateKeyRaw, pss.privateKeyRaw, recoveryKey
      );
      const recoveryCodeHash = await hashRecoveryCode(code);

      // 4. Envoi : Flask ne voit que des blobs chiffrés et des clés
      // publiques, jamais le mot de passe dérivé ni le code de
      // récupération lui-même.
      await api.post("/auth/activate-account", {
        email, token, password,
        publicKey: bytesToBase64(oaep.publicKeyRaw),
        publicKeySignature: bytesToBase64(pss.publicKeyRaw),
        encryptedPrivateKey, salt,
        recoveryEncryptedPrivateKey, recoverySalt, recoveryCodeHash,
      });

      setRecoveryCode(code);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopyRecoveryCode = async () => {
    try {
      await navigator.clipboard.writeText(recoveryCode);
      setCopied(true);
    } catch {
      // Le presse-papier peut être refusé (permissions) : l'utilisateur
      // peut toujours sélectionner/copier le texte manuellement.
    }
  };

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-brand-950">
        <Spinner size={32} className="text-white" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-white">Activation de compte</h1>
        </div>

        <div className="rounded-2xl bg-white p-6 shadow-xl">
          {!secureContext && (
            <Alert type="error" className="mb-4">
              Cette page n'est pas servie en contexte sécurisé (HTTPS ou localhost).
              Les fonctions de chiffrement du navigateur sont indisponibles ici.
            </Alert>
          )}

          {manualMode && !invitationValid && (
            <form onSubmit={handleManualSubmit} className="space-y-4">
              <Alert type="warning">
                Lien incomplet ou URL copiée sans le paramètre d’invitation. Collez l’email et le token reçus par email.
              </Alert>

              {error && <Alert type="error">{error}</Alert>}

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={manualEmail}
                  onChange={(e) => setManualEmail(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  placeholder="prenom.nom@exemple.fr"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Token d’invitation</label>
                <input
                  type="text"
                  required
                  value={manualToken}
                  onChange={(e) => setManualToken(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  placeholder="Copiez le token situé dans l’URL"
                />
              </div>

              <Button type="submit" loading={checking} className="w-full">
                Vérifier l’invitation
              </Button>

              <Link to="/connexion" className="mt-2 block text-center text-sm text-brand-600 hover:underline">
                Retour à la connexion
              </Link>
            </form>
          )}

          {!manualMode && !invitationValid && (
            <>
              <Alert type="error">{error}</Alert>
              <Link to="/connexion" className="mt-4 block text-center text-sm text-brand-600 hover:underline">
                Retour à la connexion
              </Link>
            </>
          )}

          {invitationValid && recoveryCode && (
            <div>
              <Alert type="success" className="mb-4">
                Compte activé avec succès !
              </Alert>

              <p className="mb-2 text-sm font-semibold text-slate-800">
                Votre code de récupération
              </p>
              <p className="mb-3 text-sm text-slate-600">
                Notez-le et conservez-le en lieu sûr (gestionnaire de mots de passe,
                coffre physique...). Il permet de réinitialiser votre mot de passe
                <strong> sans perdre l'accès à vos fichiers</strong> si vous l'oubliez.
                Il ne sera plus jamais affiché.
              </p>

              <div className="mb-3 rounded-lg border border-slate-300 bg-slate-50 p-3 text-center font-mono text-base tracking-wide text-slate-900">
                {recoveryCode}
              </div>

              <Button type="button" variant="secondary" className="mb-4 w-full" onClick={handleCopyRecoveryCode}>
                {copied ? "Copié ✓" : "Copier le code"}
              </Button>

              <label className="mb-4 flex items-start gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={recoveryCodeSaved}
                  onChange={(e) => setRecoveryCodeSaved(e.target.checked)}
                  className="mt-1"
                />
                J'ai noté mon code de récupération en lieu sûr. Je comprends que
                sans lui NI mon mot de passe, personne ne peut récupérer mes fichiers.
              </label>

              <Button
                type="button"
                className="w-full"
                disabled={!recoveryCodeSaved}
                onClick={() => navigate("/connexion")}
              >
                Continuer vers la connexion
              </Button>
            </div>
          )}

          {invitationValid && !recoveryCode && (
            <form onSubmit={handleSubmit}>
              <p className="mb-4 text-sm text-slate-600">
                Bienvenue <strong>{invite.prenom} {invite.nom}</strong>. Choisissez votre mot
                de passe définitif. Deux paires de clés de chiffrement seront générées pour
                vous, localement dans ce navigateur.
              </p>

              {error && <Alert type="error" className="mb-4">{error}</Alert>}

              {/* Champ caché pour que les gestionnaires de mots de passe associent
                  correctement le nouveau mot de passe à cette adresse email. */}
              <input type="hidden" name="email" autoComplete="username" value={email} readOnly />

              <div className="mb-4">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Mot de passe
                </label>
                <input
                  type="password"
                  required
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
                {password && (
                  <div className="mt-2">
                    <div className="flex h-1.5 gap-1">
                      {[0, 1, 2, 3, 4].map((i) => (
                        <div
                          key={i}
                          className={`flex-1 rounded-full ${
                            i < strength.score ? STRENGTH_COLORS[strength.score] : "bg-slate-100"
                          }`}
                        />
                      ))}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {strength.label} · {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} caractères, au moins une lettre et un chiffre
                    </p>
                  </div>
                )}
              </div>

              <div className="mb-6">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Confirmer le mot de passe
                </label>
                <input
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>

              <Alert type="warning" className="mb-4">
                Ce mot de passe ne peut pas être récupéré par un administrateur. À
                l'étape suivante, un code de récupération vous sera montré UNE SEULE
                FOIS : c'est votre seul filet de sécurité en cas d'oubli.
              </Alert>

              <Button type="submit" loading={submitting} className="w-full" disabled={!secureContext}>
                Activer mon compte
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
