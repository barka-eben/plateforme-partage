/**
 * cryptoService.js
 * ================================================================
 * Toutes les opérations cryptographiques de l'application, exécutées
 * exclusivement dans le navigateur via l'API Web Crypto (SubtleCrypto).
 *
 * Flask et PostgreSQL ne reçoivent jamais rien de ce module qui ne
 * soit déjà chiffré, hashé ou signé : c'est ce fichier qui porte, à
 * lui seul, la propriété de bout en bout de la plateforme.
 *
 * Schémas utilisés :
 *   - RSA-OAEP     : chiffrement (clé AES du fichier -> par destinataire)
 *   - RSA-PSS      : signature (preuve d'origine / non-répudiation)
 *   - AES-256-GCM  : chiffrement symétrique du contenu du fichier
 *   - PBKDF2/SHA-256 : dérivation d'une clé depuis le mot de passe
 *
 * CORRECTIF SÉCURITÉ : la version précédente utilisait UNE SEULE paire
 * RSA pour à la fois chiffrer (OAEP) et signer (PSS), ce qui contredit
 * une bonne pratique cryptographique de base (séparation des usages
 * de clé). Ce module génère désormais DEUX paires RSA-2048 distinctes
 * par utilisateur : une pour OAEP, une pour PSS. Les deux clés
 * privées sont regroupées dans un même "bundle" JSON avant d'être
 * chiffrées ensemble (un seul blob à gérer côté serveur/DB), mais
 * restent deux objects CryptoKey totalement indépendants une fois
 * importées.
 * ================================================================
 */

const RSA_MODULUS_LENGTH = 2048;
const RSA_PUBLIC_EXPONENT = new Uint8Array([0x01, 0x00, 0x01]); // 65537
const RSA_HASH = "SHA-256";
const AES_LENGTH = 256;

// Recommandation OWASP (2023+) pour PBKDF2-HMAC-SHA256. La version
// précédente utilisait 210 000, qui est la recommandation pour
// PBKDF2-HMAC-SHA512, pas SHA-256.
export const PBKDF2_ITERATIONS = 600_000;

const PSS_SALT_LENGTH = 32; // = taille d'un digest SHA-256, pratique standard

// ================================================================
// Utilitaires de conversion
// ================================================================

export function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

export function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function bytesToHex(bytes) {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

function concatBytes(...arrays) {
  const total = arrays.reduce((sum, a) => sum + a.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const arr of arrays) {
    result.set(arr, offset);
    offset += arr.length;
  }
  return result;
}

// ================================================================
// Génération et dérivation
// ================================================================

/** Génère un sel aléatoire de 16 octets, encodé en base64. */
export function generateSaltBase64() {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return bytesToBase64(salt);
}

/**
 * Dérive une clé AES-256-GCM à partir d'un secret (mot de passe OU
 * code de récupération) et d'un sel, via PBKDF2/SHA-256. Cette clé
 * sert UNIQUEMENT à chiffrer/déchiffrer le bundle de clés privées de
 * l'utilisateur — jamais à autre chose.
 */
export async function deriveKeyFromSecret(secret, saltBase64, iterations = PBKDF2_ITERATIONS) {
  const salt = base64ToBytes(saltBase64);

  const baseKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    "PBKDF2",
    false,
    ["deriveKey"]
  );

  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    baseKey,
    { name: "AES-GCM", length: AES_LENGTH },
    false, // non extractible : elle ne quitte jamais la mémoire du navigateur
    ["encrypt", "decrypt"]
  );
}

// Alias conservé pour lisibilité des appelants (mot de passe).
export const deriveKeyFromPassword = deriveKeyFromSecret;

/**
 * Génère UNE paire de clés RSA-2048 pour un usage donné ("OAEP" ou
 * "PSS"). Retournée sous forme brute (ArrayBuffer), prête à être
 * ré-importée séparément.
 */
async function generateOneRSAKeyPairRaw(usage) {
  const isOaep = usage === "OAEP";
  const keyPair = await crypto.subtle.generateKey(
    {
      name: isOaep ? "RSA-OAEP" : "RSA-PSS",
      modulusLength: RSA_MODULUS_LENGTH,
      publicExponent: RSA_PUBLIC_EXPONENT,
      hash: RSA_HASH,
    },
    true, // extractible, pour pouvoir exporter spki/pkcs8
    isOaep ? ["encrypt", "decrypt"] : ["sign", "verify"]
  );

  const publicKeyRaw = await crypto.subtle.exportKey("spki", keyPair.publicKey);
  const privateKeyRaw = await crypto.subtle.exportKey("pkcs8", keyPair.privateKey);

  return {
    publicKeyRaw: new Uint8Array(publicKeyRaw),
    privateKeyRaw: new Uint8Array(privateKeyRaw),
  };
}

/**
 * Génère les DEUX paires de clés RSA-2048 nécessaires à un compte :
 * une pour le chiffrement (OAEP), une pour la signature (PSS).
 * Générées UNE SEULE FOIS à l'activation, puis régénérées à chaque
 * changement de mot de passe (cf. ChangePassword.jsx).
 */
export async function generateKeyPairsRaw() {
  const [oaep, pss] = await Promise.all([
    generateOneRSAKeyPairRaw("OAEP"),
    generateOneRSAKeyPairRaw("PSS"),
  ]);
  return { oaep, pss };
}

// ------- Ré-import des clés brutes sous le bon algorithme -------

export async function importPublicKeyOAEP(publicKeyRaw) {
  return crypto.subtle.importKey("spki", publicKeyRaw, { name: "RSA-OAEP", hash: RSA_HASH }, true, ["encrypt"]);
}

export async function importPublicKeyPSS(publicKeyRaw) {
  return crypto.subtle.importKey("spki", publicKeyRaw, { name: "RSA-PSS", hash: RSA_HASH }, true, ["verify"]);
}

export async function importPrivateKeyOAEP(privateKeyRaw) {
  return crypto.subtle.importKey("pkcs8", privateKeyRaw, { name: "RSA-OAEP", hash: RSA_HASH }, true, ["decrypt"]);
}

export async function importPrivateKeyPSS(privateKeyRaw) {
  return crypto.subtle.importKey("pkcs8", privateKeyRaw, { name: "RSA-PSS", hash: RSA_HASH }, true, ["sign"]);
}

/**
 * Depuis la clé publique OAEP reçue du serveur (base64 SPKI, non
 * sensible), importe la clé prête à chiffrer une clé AES à
 * destination de cette personne.
 */
export async function importRemotePublicKeyOAEP(publicKeyBase64) {
  return importPublicKeyOAEP(base64ToBytes(publicKeyBase64));
}

/**
 * Depuis la clé publique PSS reçue du serveur, importe la clé prête à
 * vérifier une signature émise par cette personne.
 */
export async function importRemotePublicKeyPSS(publicKeyBase64) {
  return importPublicKeyPSS(base64ToBytes(publicKeyBase64));
}

// ================================================================
// Chiffrement / déchiffrement du BUNDLE de clés privées (au repos)
// ================================================================
// Le bundle regroupe les deux clés privées brutes (pkcs8, en base64)
// dans un seul objet JSON, chiffré comme un bloc unique. Cela évite
// de multiplier les colonnes/blobs côté serveur tout en gardant deux
// CryptoKey distincts une fois déchiffrés et réimportés.

function buildPrivateBundleJSON(oaepPrivateKeyRaw, pssPrivateKeyRaw) {
  return JSON.stringify({
    oaep: bytesToBase64(oaepPrivateKeyRaw),
    pss: bytesToBase64(pssPrivateKeyRaw),
  });
}

function parsePrivateBundleJSON(json) {
  const obj = JSON.parse(json);
  return {
    oaepPrivateKeyRaw: base64ToBytes(obj.oaep),
    pssPrivateKeyRaw: base64ToBytes(obj.pss),
  };
}

/**
 * Chiffre le bundle {oaepPriv, pssPriv} avec la clé dérivée (mot de
 * passe ou code de récupération). Retourne un blob base64 =
 * iv(12 octets) || ciphertext.
 */
export async function encryptPrivateBundle(oaepPrivateKeyRaw, pssPrivateKeyRaw, derivedKey) {
  const json = buildPrivateBundleJSON(oaepPrivateKeyRaw, pssPrivateKeyRaw);
  const plaintext = new TextEncoder().encode(json);

  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, derivedKey, plaintext);
  return bytesToBase64(concatBytes(iv, new Uint8Array(ciphertext)));
}

/**
 * Déchiffre le blob renvoyé par le serveur pour retrouver le bundle
 * de clés privées brutes. Lève une exception si le secret (mot de
 * passe ou code de récupération) est incorrect.
 */
export async function decryptPrivateBundle(blobBase64, derivedKey) {
  const blob = base64ToBytes(blobBase64);
  const iv = blob.slice(0, 12);
  const ciphertext = blob.slice(12);

  const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, derivedKey, ciphertext);
  const json = new TextDecoder().decode(plaintext);
  return parsePrivateBundleJSON(json);
}

// ================================================================
// Chiffrement AES-256-GCM du contenu d'un fichier
// ================================================================

export async function generateAESKey() {
  return crypto.subtle.generateKey({ name: "AES-GCM", length: AES_LENGTH }, true, ["encrypt", "decrypt"]);
}

export async function exportAESKeyRaw(aesKey) {
  const raw = await crypto.subtle.exportKey("raw", aesKey);
  return new Uint8Array(raw);
}

export async function importAESKeyRaw(rawBytes) {
  return crypto.subtle.importKey("raw", rawBytes, "AES-GCM", true, ["encrypt", "decrypt"]);
}

/**
 * Chiffre le contenu d'un fichier. Retourne un Blob unique
 * iv(12 octets) || ciphertext, prêt à être envoyé au serveur.
 */
export async function encryptFileContent(fileArrayBuffer, aesKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aesKey, fileArrayBuffer);
  return new Blob([iv, new Uint8Array(ciphertext)]);
}

/**
 * Déchiffre un blob iv||ciphertext reçu du serveur. Si le tag GCM ne
 * correspond pas, lève une exception (garantie d'intégrité AES-GCM,
 * en complément de la signature RSA-PSS).
 */
export async function decryptFileContent(encryptedArrayBuffer, aesKey) {
  const bytes = new Uint8Array(encryptedArrayBuffer);
  const iv = bytes.slice(0, 12);
  const ciphertext = bytes.slice(12);

  return crypto.subtle.decrypt({ name: "AES-GCM", iv }, aesKey, ciphertext);
}

// ================================================================
// Hash SHA-256 (intégrité) + Signature RSA-PSS (authenticité)
// ================================================================

export async function sha256Hex(arrayBuffer) {
  const digest = await crypto.subtle.digest("SHA-256", arrayBuffer);
  return bytesToHex(new Uint8Array(digest));
}

/** Signe le HASH avec la clé privée RSA-PSS de l'expéditeur. */
export async function signHash(hashHex, privateKeyPSS) {
  const hashBytes = hexToBytes(hashHex);
  const signature = await crypto.subtle.sign(
    { name: "RSA-PSS", saltLength: PSS_SALT_LENGTH },
    privateKeyPSS,
    hashBytes
  );
  return bytesToBase64(new Uint8Array(signature));
}

/**
 * Vérifie la signature avec la clé publique PSS de l'expéditeur.
 * Ne lève jamais d'exception pour un mismatch (verify-then-decrypt).
 */
export async function verifySignature(hashHex, signatureBase64, publicKeyPSS) {
  try {
    const hashBytes = hexToBytes(hashHex);
    const signatureBytes = base64ToBytes(signatureBase64);
    return await crypto.subtle.verify(
      { name: "RSA-PSS", saltLength: PSS_SALT_LENGTH },
      publicKeyPSS,
      signatureBytes,
      hashBytes
    );
  } catch (e) {
    return false;
  }
}

// ================================================================
// Enveloppement de la clé AES (RSA-OAEP) pour un destinataire donné
// ================================================================

export async function wrapAESKeyForRecipient(aesKeyRaw, recipientPublicKeyOAEP) {
  const encrypted = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, recipientPublicKeyOAEP, aesKeyRaw);
  return bytesToBase64(new Uint8Array(encrypted));
}

export async function unwrapAESKey(cleAesChiffreeBase64, myPrivateKeyOAEP) {
  const bytes = base64ToBytes(cleAesChiffreeBase64);
  const rawAesKey = await crypto.subtle.decrypt({ name: "RSA-OAEP" }, myPrivateKeyOAEP, bytes);
  return importAESKeyRaw(new Uint8Array(rawAesKey));
}

// ================================================================
// Code de récupération (mot de passe oublié)
// ================================================================
// Généré côté navigateur, affiché UNE SEULE FOIS à l'utilisateur.
// Haute entropie (~130 bits) : aucun ralentissement (PBKDF2) n'est
// nécessaire côté vérification serveur pour résister à une attaque
// hors-ligne, contrairement à un mot de passe choisi par un humain.

const RECOVERY_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"; // sans 0/O/1/I/L
const RECOVERY_CODE_GROUPS = 5;
const RECOVERY_GROUP_LENGTH = 5;

export function generateRecoveryCode() {
  const totalChars = RECOVERY_CODE_GROUPS * RECOVERY_GROUP_LENGTH;
  const randomBytes = crypto.getRandomValues(new Uint8Array(totalChars));
  let code = "";
  for (let i = 0; i < totalChars; i++) {
    code += RECOVERY_ALPHABET[randomBytes[i] % RECOVERY_ALPHABET.length];
  }
  const groups = [];
  for (let i = 0; i < totalChars; i += RECOVERY_GROUP_LENGTH) {
    groups.push(code.slice(i, i + RECOVERY_GROUP_LENGTH));
  }
  return groups.join("-");
}

function normalizeRecoveryCode(code) {
  return code.trim().toUpperCase().replace(/\s+/g, "");
}

/** Empreinte envoyée au serveur pour vérification rapide du code. */
export async function hashRecoveryCode(code) {
  const normalized = normalizeRecoveryCode(code);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normalized));
  return bytesToHex(new Uint8Array(digest));
}

/** Dérive la clé de chiffrement du bundle de récupération. */
export async function deriveKeyFromRecoveryCode(code, saltBase64, iterations = PBKDF2_ITERATIONS) {
  return deriveKeyFromSecret(normalizeRecoveryCode(code), saltBase64, iterations);
}

// ================================================================
// Estimation grossière de robustesse d'un mot de passe (feedback UI
// uniquement — la vraie barrière est côté serveur, cf. auth_service.py)
// ================================================================

export function estimatePasswordStrength(password) {
  let score = 0;
  if (!password) return { score: 0, label: "Vide" };

  if (password.length >= 10) score++;
  if (password.length >= 14) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  const labels = ["Très faible", "Faible", "Moyen", "Bon", "Fort", "Très fort"];
  return { score, label: labels[Math.min(score, labels.length - 1)] };
}
