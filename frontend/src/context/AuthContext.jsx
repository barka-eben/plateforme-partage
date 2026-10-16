/**
 * context/AuthContext.jsx
 * ================================================================
 * Contexte d'authentification.
 *
 * IMPORTANT (cf. cahier des charges §3.1) : le token JWT et les clés
 * privées déchiffrées ne sont conservés QU'EN MÉMOIRE (useState), sans
 * jamais toucher localStorage/sessionStorage. C'est un compromis
 * assumé : un rechargement de page (F5) ou une fermeture d'onglet
 * déconnecte l'utilisateur et efface ses clés privées déchiffrées de
 * la mémoire du navigateur. C'est le prix de la garantie que la clé
 * privée ne "fuit" jamais vers un support persistant accessible par
 * un script (XSS) ou un autre utilisateur du même poste.
 *
 * CORRECTIFS PAR RAPPORT À LA VERSION PRÉCÉDENTE :
 *  - /auth/login renvoie désormais directement cle_publique ET
 *    cle_publique_signature : le blocage total de l'envoi de fichiers
 *    (myPublicKeyOAEP valait systématiquement null) est corrigé.
 *  - Deux paires de clés (OAEP / PSS) sont gérées séparément, issues
 *    d'un même "bundle" chiffré (cf. cryptoService.decryptPrivateBundle).
 *  - Un 401 de session (token expiré/révoqué) déclenche désormais une
 *    déconnexion propre avec message, via setUnauthorizedHandler.
 * ================================================================
 */

import { createContext, useContext, useState, useCallback, useMemo, useEffect } from "react";
import { api, setAuthToken, setUnauthorizedHandler } from "../services/api";
import {
  deriveKeyFromPassword,
  decryptPrivateBundle,
  encryptPrivateBundle,
  importPrivateKeyOAEP,
  importPrivateKeyPSS,
  importRemotePublicKeyOAEP,
  generateSaltBase64,
} from "../crypto/cryptoService";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [accountNeedsActivation, setAccountNeedsActivation] = useState(false);
  const [sessionMessage, setSessionMessage] = useState(null);

  // Clés brutes / importées, gardées UNIQUEMENT en mémoire vive.
  const [oaepPrivateKeyRaw, setOaepPrivateKeyRaw] = useState(null); // pour re-chiffrer au changement de mdp
  const [pssPrivateKeyRaw, setPssPrivateKeyRaw] = useState(null);
  const [privateKeyOAEP, setPrivateKeyOAEP] = useState(null); // pour déchiffrer les clés AES reçues
  const [privateKeyPSS, setPrivateKeyPSS] = useState(null); // pour signer mes envois
  const [publicKeyOAEP, setPublicKeyOAEP] = useState(null); // ma propre clé publique (pour m'auto-chiffrer)

  const isAuthenticated = Boolean(token && user);
  const isCryptoUnlocked = Boolean(privateKeyOAEP && privateKeyPSS);

  const clearSession = useCallback((message = null) => {
    setToken(null);
    setUser(null);
    setAccountNeedsActivation(false);
    setOaepPrivateKeyRaw(null);
    setPssPrivateKeyRaw(null);
    setPrivateKeyOAEP(null);
    setPrivateKeyPSS(null);
    setPublicKeyOAEP(null);
    setAuthToken(null);
    setSessionMessage(message);
  }, []);

  // Enregistre le handler de 401 "de session" une seule fois. Sans ce
  // branchement, un token expiré ou révoqué (déconnexion forcée,
  // changement de mot de passe ailleurs) laissait l'UI "connectée"
  // en apparence, enchaînant des erreurs à chaque appel.
  useEffect(() => {
    setUnauthorizedHandler((message) => {
      clearSession(message || "Votre session a expiré. Reconnectez-vous.");
    });
  }, [clearSession]);

  /**
   * Connexion complète : authentifie auprès de Flask, PUIS dérive
   * localement la clé à partir du mot de passe pour déchiffrer le
   * bundle de clés privées RSA. Le mot de passe ne sert plus après
   * cette étape et n'est jamais transmis nulle part sous forme dérivée.
   */
  const login = useCallback(async (email, password) => {
    const data = await api.post("/auth/login", { email, password });

    const hasCryptoMaterial = Boolean(data.cle_privee_chiffree && data.sel_derivation_cle);
    const needsActivation = !hasCryptoMaterial;

    setAccountNeedsActivation(needsActivation);
    setAuthToken(data.access_token);
    setSessionMessage(null);

    let oaepRaw = null;
    let pssRaw = null;
    let privOAEP = null;
    let privPSS = null;
    let pubOAEP = null;

    if (hasCryptoMaterial) {
      const derivedKey = await deriveKeyFromPassword(
        password,
        data.sel_derivation_cle,
        data.pbkdf2_iterations || undefined
      );

      try {
        const bundle = await decryptPrivateBundle(data.cle_privee_chiffree, derivedKey);
        oaepRaw = bundle.oaepPrivateKeyRaw;
        pssRaw = bundle.pssPrivateKeyRaw;
      } catch (e) {
        setAuthToken(null);
        throw new Error(
          "Impossible de déchiffrer votre clé privée. Le mot de passe est-il correct ?"
        );
      }

      [privOAEP, privPSS] = await Promise.all([
        importPrivateKeyOAEP(oaepRaw),
        importPrivateKeyPSS(pssRaw),
      ]);

      // Correctif : le serveur renvoie maintenant directement les
      // deux clés publiques au login (auparavant absentes de la
      // réponse), ce qui débloque l'envoi de fichiers pour tout le
      // monde, y compris l'administrateur.
      if (data.cle_publique) {
        pubOAEP = await importRemotePublicKeyOAEP(data.cle_publique);
      }
    }

    setToken(data.access_token);
    setUser(data.user);
    setOaepPrivateKeyRaw(oaepRaw);
    setPssPrivateKeyRaw(pssRaw);
    setPrivateKeyOAEP(privOAEP);
    setPrivateKeyPSS(privPSS);
    setPublicKeyOAEP(pubOAEP);

    return {
      user: data.user,
      needsActivation,
    };
  }, []);

  const logout = useCallback(() => {
    clearSession(null);
  }, [clearSession]);

  /**
   * Changement de mot de passe : régénère un nouveau sel et re-chiffre
   * le bundle de clés privées déjà en mémoire avec une clé dérivée du
   * NOUVEAU mot de passe, puis envoie uniquement le nouveau blob
   * chiffré au serveur (jamais les clés en clair, jamais le nouveau
   * mot de passe sous une autre forme que son hash bcrypt côté API).
   */
  const changePassword = useCallback(
    async (currentPassword, newPassword) => {
      if (!oaepPrivateKeyRaw || !pssPrivateKeyRaw) {
        throw new Error("Clés privées non disponibles en mémoire, reconnectez-vous.");
      }

      const newSalt = generateSaltBase64();
      const newDerivedKey = await deriveKeyFromPassword(newPassword, newSalt);
      const newEncryptedBundle = await encryptPrivateBundle(
        oaepPrivateKeyRaw,
        pssPrivateKeyRaw,
        newDerivedKey
      );

      const result = await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
        encryptedPrivateKey: newEncryptedBundle,
        salt: newSalt,
      });

      // Le backend a incrémenté jwt_epoch (révocation des anciens
      // tokens) et renvoie un nouveau token valide pour la session
      // courante, pour éviter de se déconnecter soi-même.
      if (result.access_token) {
        setToken(result.access_token);
        setAuthToken(result.access_token);
      }
    },
    [oaepPrivateKeyRaw, pssPrivateKeyRaw]
  );

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated,
      isCryptoUnlocked,
      accountNeedsActivation,
      sessionMessage,
      clearSessionMessage: () => setSessionMessage(null),
      privateKeyOAEP,
      privateKeyPSS,
      publicKeyOAEP,
      login,
      logout,
      changePassword,
    }),
    [
      token,
      user,
      isAuthenticated,
      isCryptoUnlocked,
      accountNeedsActivation,
      sessionMessage,
      privateKeyOAEP,
      privateKeyPSS,
      publicKeyOAEP,
      login,
      logout,
      changePassword,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un <AuthProvider>");
  return ctx;
}
