/**
 * services/api.js
 * ================================================================
 * Petit wrapper autour de fetch() qui :
 *  - préfixe toutes les requêtes avec l'URL de base de l'API,
 *  - ajoute l'en-tête Authorization: Bearer <token> quand disponible,
 *  - normalise la gestion des erreurs (le corps JSON d'erreur Flask
 *    est toujours de la forme { message: "..." }),
 *  - signale un 401 à l'application (session expirée / révoquée) via
 *    un callback enregistré par AuthContext, plutôt que de laisser
 *    l'interface "connectée" enchaîner des erreurs silencieuses
 *    (correctif : absence totale de traitement du 401 auparavant).
 *
 * Ce module ne contient AUCUNE logique cryptographique : il ne fait
 * que transporter des blobs déjà chiffrés/signés par cryptoService.js.
 * ================================================================
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000/api";

let authToken = null;

/** Appelé par AuthContext lors du login / logout / restauration. */
export function setAuthToken(token) {
  authToken = token;
}

// Chemins pour lesquels un 401 est un résultat ATTENDU (mauvais
// identifiants, code de récupération invalide...) et ne doit donc
// jamais déclencher une déconnexion globale.
const PATHS_EXEMPTS_DU_HANDLER_401 = [
  "/auth/login",
  "/auth/change-password",
];

let onUnauthorized = null;

/**
 * Enregistre le callback appelé lors d'un 401 "de session" (token
 * expiré ou révoqué). AuthContext l'utilise pour vider la session et
 * rediriger vers /connexion, plutôt que de laisser l'UI dans un état
 * incohérent (correctif "aucun traitement du 401").
 */
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request(path, { method = "GET", body, isFormData = false, headers = {} } = {}) {
  const finalHeaders = { ...headers };

  if (authToken) {
    finalHeaders["Authorization"] = `Bearer ${authToken}`;
  }

  let finalBody = body;

  if (body && !isFormData) {
    finalHeaders["Content-Type"] = "application/json";
    finalBody = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: finalHeaders,
      body: finalBody,
    });
  } catch (networkError) {
    throw new ApiError(
      "Impossible de contacter le serveur. Vérifiez votre connexion ou que l'API est démarrée.",
      0,
      null
    );
  }

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;

  if (response.status === 401 && authToken && !PATHS_EXEMPTS_DU_HANDLER_401.includes(path)) {
    // Un token qu'on croyait valide vient d'être rejeté : session
    // expirée (8h) ou révoquée (mot de passe changé / compte
    // désactivé ailleurs, cf. jwt_epoch côté backend). On informe
    // immédiatement l'application plutôt que de laisser l'appelant
    // gérer chaque cas isolément.
    if (onUnauthorized) onUnauthorized(data && data.message);
  }

  if (!response.ok) {
    throw new ApiError(
      (data && data.message) || `Erreur ${response.status}`,
      response.status,
      data
    );
  }

  return data;
}

export const api = {
  get: (path) => request(path, { method: "GET" }),
  post: (path, body) => request(path, { method: "POST", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  delete: (path) => request(path, { method: "DELETE" }),
  postForm: (path, formData) =>
    request(path, { method: "POST", body: formData, isFormData: true }),

  /** Téléchargement binaire brut (pour récupérer un fichier chiffré). */
  async getBinary(path) {
    const finalHeaders = {};
    if (authToken) finalHeaders["Authorization"] = `Bearer ${authToken}`;

    const response = await fetch(`${API_URL}${path}`, { headers: finalHeaders });

    if (response.status === 401 && authToken && onUnauthorized) {
      const data = await response.json().catch(() => null);
      onUnauthorized(data && data.message);
    }

    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new ApiError((data && data.message) || `Erreur ${response.status}`, response.status, data);
    }
    return response.arrayBuffer();
  },
};

export { ApiError };
