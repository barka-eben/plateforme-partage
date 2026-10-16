import { useEffect, useState, useCallback } from "react";
import { api } from "../../services/api";
import { Card, EmptyState } from "../../components/common/Card";
import Badge from "../../components/common/Badge";
import Select from "../../components/common/Select";
import Input from "../../components/common/Input";
import Button from "../../components/common/Button";
import Alert from "../../components/common/Alert";
import Spinner from "../../components/common/Spinner";

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
  RENVOI_INVITATION: "Renvoi d'invitation",
  SUPPRESSION_COMPTE_EN_ATTENTE: "Suppression d'un compte en attente",
  RECUPERATION_COMPTE: "Récupération de compte (mot de passe oublié)",
  ECHEC_RECUPERATION_COMPTE: "Échec de récupération de compte",
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

export default function AdminJournal() {
  const [entries, setEntries] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: String(page), per_page: "30" });
      if (actionFilter) params.set("action", actionFilter);
      const data = await api.get(`/history/admin/journal?${params.toString()}`);
      setEntries(data.journal);
      setTotalPages(data.total_pages || 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold text-slate-900">Journal global d'activité</h1>
      <p className="mb-6 text-sm text-slate-500">
        Traçabilité complète des actions effectuées sur la plateforme.
      </p>

      <div className="mb-4 flex gap-3">
        <Select
          className="max-w-xs"
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Toutes les actions</option>
          {Object.entries(ACTION_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : entries.length === 0 ? (
          <EmptyState icon="📜" title="Aucune entrée trouvée" />
        ) : (
          <div className="divide-y divide-slate-100">
            {entries.map((h) => (
              <div key={h.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {ACTION_LABELS[h.action] || h.action}
                    {h.utilisateur && (
                      <span className="ml-1 font-normal text-slate-500">
                        par {h.utilisateur.prenom} {h.utilisateur.nom}
                      </span>
                    )}
                    {h.cible && (
                      <span className="ml-1 font-normal text-slate-500">
                        → {h.cible.prenom} {h.cible.nom}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatDate(h.date_action)}
                    {h.ip_adresse && <span> · {h.ip_adresse}</span>}
                  </p>
                  {h.detail && (
                    <p className="text-xs text-slate-400">{h.detail}</p>
                  )}
                </div>
                <Badge color={h.statut_action ? "green" : "red"}>
                  {h.statut_action ? "Succès" : "Échec"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Précédent
          </Button>
          <span className="text-sm text-slate-500">
            Page {page} / {totalPages}
          </span>
          <Button
            variant="secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Suivant
          </Button>
        </div>
      )}
    </div>
  );
}
