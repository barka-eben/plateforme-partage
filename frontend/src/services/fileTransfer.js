/**
 * services/fileTransfer.js
 * ================================================================
 * Orchestration de haut niveau des deux opérations sensibles de
 * l'application : l'envoi (chiffrer + signer + diffuser) et la
 * réception (vérifier puis déchiffrer, jamais l'inverse) d'un
 * fichier. Toute la cryptographie passe par cryptoService.js ;
 * ce module ne fait que l'orchestrer avec les appels API.
 * ================================================================
 */

import { api } from "./api";
import {
  generateAESKey,
  exportAESKeyRaw,
  encryptFileContent,
  decryptFileContent,
  sha256Hex,
  signHash,
  verifySignature,
  wrapAESKeyForRecipient,
  unwrapAESKey,
  importRemotePublicKeyOAEP,
  importRemotePublicKeyPSS,
} from "../crypto/cryptoService";

/**
 * Chiffre puis envoie un fichier à une liste de destinataires déjà
 * résolue (avec leurs clés publiques OAEP/PSS en base64).
 *
 * @param {File} file - le fichier choisi par l'utilisateur
 * @param {Array<{id:string, cle_publique:string}>} destinataires
 * @param {CryptoKey} privateKeyPSS - pour signer le hash
 * @param {CryptoKey} myPublicKeyOAEP - pour me garder une copie lisible
 * @param {(step:string, current:number, total:number)=>void} onProgress
 * @param {{mode?: "user"|"niveau"|"all", targetNiveauId?: string, targetStructureId?: string}} meta
 *        Transmis au serveur pour qu'il puisse REVÉRIFIER l'autorisation
 *        de diffusion (correctif : l'upload n'appliquait auparavant
 *        aucune règle, seul /targets/resolve le faisait, et rien
 *        n'empêchait de l'appeler directement en le contournant).
 */
export async function sendFile(file, destinataires, privateKeyPSS, myPublicKeyOAEP, onProgress, meta = {}) {
  const total = destinataires.length + 3; // +chiffrement, +signature, +upload
  let step = 0;
  const report = (label) => onProgress && onProgress(label, ++step, total);

  if (!myPublicKeyOAEP) {
    throw new Error(
      "Votre clé publique de chiffrement n'est pas disponible : reconnectez-vous."
    );
  }

  report("Lecture du fichier");
  const fileBuffer = await file.arrayBuffer();

  report("Calcul de l'empreinte SHA-256");
  const hashHex = await sha256Hex(fileBuffer);

  report("Signature de l'empreinte");
  const signature = await signHash(hashHex, privateKeyPSS);

  report("Génération de la clé de chiffrement du fichier");
  const aesKey = await generateAESKey();
  const aesKeyRaw = await exportAESKeyRaw(aesKey);

  const encryptedBlob = await encryptFileContent(fileBuffer, aesKey);

  // Une copie de la clé AES chiffrée avec ma PROPRE clé publique,
  // pour pouvoir rouvrir mes propres envois plus tard.
  const cleAesChiffreeExpediteur = await wrapAESKeyForRecipient(aesKeyRaw, myPublicKeyOAEP);

  const diffusions = [];
  const destinatairesSansCle = [];

  for (const dest of destinataires) {
    if (!dest.cle_publique) {
      // Ne devrait plus arriver (le serveur filtre désormais ces
      // comptes dans /targets/resolve), mais on reste défensif :
      // un seul destinataire sans clé ne doit plus faire échouer
      // l'envoi à tous les autres.
      destinatairesSansCle.push(dest);
      continue;
    }
    report(`Chiffrement de la clé pour ${dest.prenom ? dest.prenom + " " + dest.nom : dest.id}`);
    const oaep = await importRemotePublicKeyOAEP(dest.cle_publique);
    const cle_aes_chiffree = await wrapAESKeyForRecipient(aesKeyRaw, oaep);
    diffusions.push({ destinataire_id: dest.id, cle_aes_chiffree });
  }

  if (diffusions.length === 0) {
    throw new Error(
      "Aucun destinataire exploitable (clé de chiffrement manquante). Envoi annulé."
    );
  }

  report("Envoi au serveur");
  const formData = new FormData();
  formData.append("file", encryptedBlob, "chiffre.bin");
  formData.append("hash_sha256", hashHex);
  formData.append("signature", signature);
  formData.append("nom_chiffre", file.name);
  formData.append("cle_aes_chiffree_expediteur", cleAesChiffreeExpediteur);
  formData.append("diffusions", JSON.stringify(diffusions));
  formData.append("mode", meta.mode || "user");
  if (meta.targetNiveauId) formData.append("target_niveau_id", meta.targetNiveauId);
  if (meta.targetStructureId) formData.append("target_structure_id", meta.targetStructureId);

  const result = await api.postForm("/files/upload", formData);

  return { ...result, destinatairesIgnores: destinatairesSansCle };
}

/**
 * Télécharge, VÉRIFIE la signature puis (seulement si elle est
 * valide) déchiffre un fichier. Ne déchiffre jamais avant d'avoir
 * vérifié : c'est le principe "verify-then-decrypt" du cahier des
 * charges (§5.4), qui évite de traiter un contenu falsifié.
 *
 * Retourne { blob, filename, signatureValide }.
 * Journalise systématiquement le résultat auprès du serveur.
 */
export async function downloadAndDecryptFile(fichierId, myPrivateKeyOAEP) {
  const meta = await api.get(`/files/${fichierId}`);

  const senderPublicKeyPSS = await importRemotePublicKeyPSS(meta.cle_publique_expediteur);

  const signatureValide = await verifySignature(
    meta.hash_sha256,
    meta.signature,
    senderPublicKeyPSS
  );

  if (!signatureValide) {
    await api.post(`/files/${fichierId}/confirm-download`, { signature_valide: false });
    throw new Error(
      "La signature numérique de ce fichier est invalide : son intégrité ou son " +
        "origine ne peut pas être garantie. Le fichier n'a PAS été déchiffré."
    );
  }

  const aesKey = await unwrapAESKey(meta.cle_aes_chiffree, myPrivateKeyOAEP);

  // atob/base64 -> ArrayBuffer pour les données chiffrées reçues en JSON
  const binary = atob(meta.donnee_chiffree);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const decrypted = await decryptFileContent(bytes.buffer, aesKey);

  // Vérification d'intégrité supplémentaire : le hash du contenu
  // déchiffré doit correspondre au hash signé par l'expéditeur.
  const recomputedHash = await sha256Hex(decrypted);
  const hashMatches = recomputedHash === meta.hash_sha256;

  await api.post(`/files/${fichierId}/confirm-download`, {
    signature_valide: hashMatches,
  });

  if (!hashMatches) {
    throw new Error(
      "Le contenu déchiffré ne correspond pas à l'empreinte signée. Le fichier a " +
        "peut-être été corrompu ou altéré."
    );
  }

  await api.put(`/files/${fichierId}/mark-read`);

  return {
    blob: new Blob([decrypted]),
    filename: meta.nom_chiffre,
    expediteurNom: meta.expediteur_nom,
    dateDepot: meta.date_depot,
  };
}

export function triggerBrowserDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
