import { useEffect, useState } from "react";
import { api } from "../services/api";
import { Card, EmptyState } from "../components/common/Card";
import Badge from "../components/common/Badge";
import Spinner from "../components/common/Spinner";
import Alert from "../components/common/Alert";

const ACTION_LABELS = {
  CONNEXION: "Connexion",
  DEPOT_FICHIER: "Dépôt de fichier",
  TELECHARGEMENT: "Téléchargement",
  ECHEC_VERIFICATION_SIGNATURE: "Échec de vérification de signature",
  ACTIVATION_COMPTE: "Activation du compte",
  CHANGEMENT_MOT_DE_PASSE: "Changement de mot de passe",
  CREATION_COMPTE: "Création de compte",
  MODIFICATION_COMPTE: "Modification de compte",
  REACTIVATION_COMPTE: "Réactivation de compte",
  DESACTIVATION_COMPTE: "Désactivation de compte",
};

function formatDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function History() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/history")
      .then((d) => setEntries(d.historique))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold text-slate-900">Mon historique</h1>
      <p className="mb-6 text-sm text-slate-500">
        Les 100 dernières actions liées à votre compte.
      </p>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : entries.length === 0 ? (
          <EmptyState icon="🕓" title="Aucune activité pour l'instant" />
        ) : (
          <div className="divide-y divide-slate-100">
            {entries.map((h) => (
              <div key={h.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {ACTION_LABELS[h.action] || h.action}
                  </p>
                  <p className="text-xs text-slate-500">{formatDate(h.date_action)}</p>
                </div>
                <Badge color={h.statut_action ? "green" : "red"}>
                  {h.statut_action ? "Succès" : "Échec"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
