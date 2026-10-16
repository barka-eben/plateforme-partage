import { useState, useEffect, useCallback } from "react";
import { api } from "../../services/api";
import Input from "../common/Input";
import Select from "../common/Select";
import Alert from "../common/Alert";
import Badge from "../common/Badge";

/**
 * onResolved(destinataires, meta) où meta = { mode, targetNiveauId,
 * targetStructureId }. Le meta est transmis jusqu'à sendFile() puis
 * jusqu'au serveur, qui revérifie l'autorisation de diffusion au
 * moment de l'upload (cf. correctif file_routes.py :
 * _check_broadcast_authorization).
 */
export default function RecipientPicker({ onResolved }) {
  const [mode, setMode] = useState("user"); // "user" | "niveau" | "all"

  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const [niveaux, setNiveaux] = useState([]);
  const [structures, setStructures] = useState([]);
  const [selectedNiveau, setSelectedNiveau] = useState("");
  const [selectedStructure, setSelectedStructure] = useState("");

  const [resolved, setResolved] = useState([]);
  const [ignoresSansCle, setIgnoresSansCle] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/admin/niveaux").then((d) => setNiveaux(d.niveaux)).catch(() => {});
    api.get("/admin/structures").then((d) => setStructures(d.structures)).catch(() => {});
  }, []);

  // Recherche debouncée par nom/prénom/email
  useEffect(() => {
    if (mode !== "user" || query.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    const handle = setTimeout(async () => {
      try {
        const data = await api.get(`/users/search?q=${encodeURIComponent(query)}`);
        setSearchResults(data.utilisateurs);
      } catch (err) {
        // silencieux : la recherche n'est pas critique
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(handle);
  }, [query, mode]);

  const notifyParent = (destinataires, extra = {}) => {
    onResolved(destinataires, {
      mode,
      targetNiveauId: selectedNiveau || null,
      targetStructureId: selectedStructure || null,
      ...extra,
    });
  };

  const addUser = (user) => {
    if (resolved.find((r) => r.id === user.id)) return;
    const updated = [...resolved, user];
    setResolved(updated);
    onResolved(updated, { mode: "user" });
    setQuery("");
    setSearchResults([]);
  };

  const removeUser = (id) => {
    const updated = resolved.filter((r) => r.id !== id);
    setResolved(updated);
    onResolved(updated, { mode: "user" });
  };

  /**
   * CORRECTIF (closure périmée) : la version précédente lisait
   * `selectedStructure` depuis la closure du composant au moment de
   * l'appel, qui contenait encore l'ANCIENNE valeur juste après un
   * setSelectedStructure() dans le même gestionnaire d'événement (les
   * mises à jour de state React ne sont pas synchrones). Résultat :
   * changer la structure relançait la résolution avec un cran de
   * retard. On accepte désormais un override explicite plutôt que de
   * compter sur la closure.
   */
  const resolveTarget = useCallback(
    async (type, targetId, structureIdOverride) => {
      setError("");
      setLoading(true);
      try {
        const body = { type };
        if (targetId) body.target_id = targetId;

        const structureToUse = structureIdOverride !== undefined
          ? structureIdOverride
          : selectedStructure;
        if (structureToUse) body.structure_id = structureToUse;

        const data = await api.post("/targets/resolve", body);
        setResolved(data.destinataires);
        setIgnoresSansCle(data.destinataires_ignores_sans_cle || 0);
        onResolved(data.destinataires, {
          mode: type,
          targetNiveauId: targetId || null,
          targetStructureId: structureToUse || null,
        });
      } catch (err) {
        setError(err.message);
        setResolved([]);
        setIgnoresSansCle(0);
        onResolved([], { mode: type });
      } finally {
        setLoading(false);
      }
    },
    [selectedStructure, onResolved]
  );

  const handleModeChange = (newMode) => {
    setMode(newMode);
    setResolved([]);
    setIgnoresSansCle(0);
    onResolved([], { mode: newMode });
    setError("");
    if (newMode === "all") {
      resolveTarget("all");
    }
  };

  return (
    <div>
      <div className="mb-4 flex gap-2">
        {[
          { key: "user", label: "Une personne précise" },
          { key: "niveau", label: "Un niveau hiérarchique" },
          { key: "all", label: "Tous les utilisateurs" },
        ].map((opt) => (
          <button
            key={opt.key}
            type="button"
            onClick={() => handleModeChange(opt.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              mode === opt.key
                ? "bg-brand-700 text-white"
                : "bg-white text-slate-600 border border-slate-200"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && <Alert type="error" className="mb-3">{error}</Alert>}

      {ignoresSansCle > 0 && (
        <Alert type="warning" className="mb-3">
          {ignoresSansCle} compte(s) ignoré(s) car n'ayant pas encore activé leur
          compte (aucune clé de chiffrement disponible).
        </Alert>
      )}

      {mode === "user" && (
        <div className="mb-3">
          <Input
            placeholder="Rechercher par nom, prénom ou email..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {searching && <p className="mt-1 text-xs text-slate-400">Recherche...</p>}
          {searchResults.length > 0 && (
            <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-sm">
              {searchResults.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => addUser(u)}
                  disabled={!u.cle_publique}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  title={!u.cle_publique ? "Compte pas encore activé (aucune clé de chiffrement)" : ""}
                >
                  <span>
                    {u.prenom} {u.nom}{" "}
                    <span className="text-slate-400">— {u.poste_administratif}</span>
                  </span>
                  <span className="text-xs text-brand-600">
                    {u.cle_publique ? "Ajouter" : "Compte inactif"}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === "niveau" && (
        <div className="mb-3 grid grid-cols-2 gap-3">
          <Select
            label="Niveau cible"
            value={selectedNiveau}
            onChange={(e) => {
              const niveauId = e.target.value;
              setSelectedNiveau(niveauId);
              if (niveauId) resolveTarget("niveau", niveauId);
            }}
          >
            <option value="">Sélectionner un niveau...</option>
            {niveaux.map((n) => (
              <option key={n.id} value={n.id}>
                {n.libelle}
              </option>
            ))}
          </Select>
          <Select
            label="Structure (optionnel)"
            value={selectedStructure}
            onChange={(e) => {
              const structureId = e.target.value;
              setSelectedStructure(structureId);
              if (selectedNiveau) resolveTarget("niveau", selectedNiveau, structureId);
            }}
          >
            <option value="">Ma structure et ses unités</option>
            {structures.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nom}
              </option>
            ))}
          </Select>
        </div>
      )}

      {mode === "all" && (
        <Alert type="warning" className="mb-3">
          Ce document sera diffusé à tous les utilisateurs actifs de la plateforme.
        </Alert>
      )}

      {loading && <p className="text-sm text-slate-400">Résolution des destinataires...</p>}

      {resolved.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            {resolved.length} destinataire(s) sélectionné(s)
          </p>
          <div className="flex flex-wrap gap-2">
            {resolved.map((u) => (
              <Badge key={u.id} color="blue">
                <span className="mr-1">
                  {u.prenom} {u.nom}
                </span>
                {mode === "user" && (
                  <button
                    type="button"
                    onClick={() => removeUser(u.id)}
                    className="ml-1 text-brand-800 hover:text-red-600"
                  >
                    ✕
                  </button>
                )}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
