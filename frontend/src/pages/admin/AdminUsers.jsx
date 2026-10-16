import { useEffect, useState, useCallback } from "react";
import { api } from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { Card, CardHeader, EmptyState } from "../../components/common/Card";
import Badge from "../../components/common/Badge";
import Button from "../../components/common/Button";
import Input from "../../components/common/Input";
import Select from "../../components/common/Select";
import Modal from "../../components/common/Modal";
import Alert from "../../components/common/Alert";
import Spinner from "../../components/common/Spinner";

const STATUT_BADGE = {
  ACTIF: "green",
  EN_ATTENTE: "amber",
  INACTIF: "red",
};
const STATUT_LABEL = {
  ACTIF: "Actif",
  EN_ATTENTE: "En attente d'activation",
  INACTIF: "Désactivé",
};

function UserForm({ initial, niveaux, structures, onSubmit, submitting, error, isAdmin }) {
  const [form, setForm] = useState(
    initial || {
      nom: "",
      prenom: "",
      email: "",
      poste_administratif: "",
      niveau_id: "",
      structure_id: "",
    }
  );

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
      className="space-y-3"
    >
      {error && <Alert type="error">{error}</Alert>}
      <div className="grid grid-cols-2 gap-3">
        <Input label="Prénom" required value={form.prenom} onChange={set("prenom")} />
        <Input label="Nom" required value={form.nom} onChange={set("nom")} />
      </div>
      <div>
        <Input
          label="Email"
          type="email"
          required
          value={form.email}
          onChange={set("email")}
        />
        {initial && (
          <p className="mt-1 text-xs text-slate-500">
            Modifier l'email d'un compte déjà activé n'affecte pas ses clés de
            chiffrement. Pour un compte en attente, cela corrige simplement
            l'adresse qui recevra l'invitation.
          </p>
        )}
      </div>
      <Input
        label="Poste administratif"
        required
        value={form.poste_administratif}
        onChange={set("poste_administratif")}
      />
      <div className="grid grid-cols-2 gap-3">
        <Select label="Niveau" required value={form.niveau_id} onChange={set("niveau_id")}>
          <option value="">Sélectionner...</option>
          {niveaux.map((n) => (
            <option key={n.id} value={n.id}>
              {n.libelle}
            </option>
          ))}
        </Select>
        <Select
          label="Structure"
          required
          value={form.structure_id}
          onChange={set("structure_id")}
        >
          <option value="">Sélectionner...</option>
          {structures.map((s) => (
            <option key={s.id} value={s.id}>
              {s.nom}
            </option>
          ))}
        </Select>
      </div>

      {initial && isAdmin && (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={Boolean(form.est_administrateur_systeme)}
            onChange={(e) => setForm({ ...form, est_administrateur_systeme: e.target.checked })}
          />
          Administrateur système
        </label>
      )}

      <Button type="submit" loading={submitting} className="w-full">
        {initial ? "Enregistrer les modifications" : "Créer le compte"}
      </Button>
    </form>
  );
}

export default function AdminUsers() {
  const { user: currentUser } = useAuth();
  const isAdmin = Boolean(currentUser?.est_administrateur_systeme);

  const [users, setUsers] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [structures, setStructures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirmingDeactivate, setConfirmingDeactivate] = useState(null);
  const [confirmingDelete, setConfirmingDelete] = useState(null);
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [devLink, setDevLink] = useState("");
  const [infoMessage, setInfoMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      params.set("page", String(page));
      params.set("per_page", "20");

      const [u, n, s] = await Promise.all([
        api.get(`/admin/users?${params.toString()}`),
        api.get("/admin/niveaux"),
        api.get("/admin/structures"),
      ]);
      setUsers(u.utilisateurs);
      setTotalPages(u.total_pages || 1);
      setNiveaux(n.niveaux);
      setStructures(s.structures);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    setPage(1);
  }, [search]);

  useEffect(() => {
    const handle = setTimeout(load, 250);
    return () => clearTimeout(handle);
  }, [load]);

  const handleCreate = async (form) => {
    setSubmitting(true);
    setFormError("");
    setDevLink("");
    try {
      const data = await api.post("/admin/users", form);
      if (data.lien_activation_dev) {
        setDevLink(data.lien_activation_dev);
      } else {
        setShowCreate(false);
        setInfoMessage(
          `Compte créé pour ${form.email}. L'invitation a été envoyée par email ` +
            "(ou affichée dans les logs du serveur en l'absence de SMTP configuré)."
        );
      }
      load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (form) => {
    setSubmitting(true);
    setFormError("");
    try {
      await api.put(`/admin/users/${editing.id}`, form);
      setEditing(null);
      load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const doDeactivate = async (user) => {
    setError("");
    try {
      await api.post(`/admin/users/${user.id}/deactivate`);
      setConfirmingDeactivate(null);
      load();
    } catch (err) {
      setError(err.message);
      setConfirmingDeactivate(null);
    }
  };

  const doReactivate = async (user) => {
    setError("");
    try {
      await api.post(`/admin/users/${user.id}/activate`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const doDelete = async (user) => {
    setError("");
    try {
      await api.delete(`/admin/users/${user.id}`);
      setConfirmingDelete(null);
      load();
    } catch (err) {
      setError(err.message);
      setConfirmingDelete(null);
    }
  };

  const resendInvitation = async (user) => {
    setError("");
    setInfoMessage("");
    try {
      const data = await api.post(`/admin/users/${user.id}/resend-invitation`);
      if (data.lien_activation_dev) {
        setDevLink(data.lien_activation_dev);
      } else {
        setInfoMessage(`Invitation renvoyée à ${user.email}.`);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Gestion des comptes</h1>
          <p className="mt-1 text-sm text-slate-500">
            {isAdmin
              ? "Provisionner, modifier, activer ou désactiver des comptes utilisateurs."
              : "Provisionner des comptes de niveau inférieur au vôtre, dans votre structure ou une structure descendante."}
          </p>
        </div>
        <Button onClick={() => { setShowCreate(true); setFormError(""); setDevLink(""); }}>
          + Créer un compte
        </Button>
      </div>

      {devLink && (
        <Alert type="info" className="mb-4">
          Mode développement — aucun SMTP configuré. Lien d'activation :{" "}
          <a href={devLink} className="underline break-all">{devLink}</a>
        </Alert>
      )}

      {infoMessage && (
        <Alert type="success" className="mb-4">{infoMessage}</Alert>
      )}

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <div className="mb-4 max-w-sm">
        <Input
          placeholder="Rechercher par nom, prénom, email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : users.length === 0 ? (
          <EmptyState icon="👤" title="Aucun utilisateur trouvé" />
        ) : (
          <div className="divide-y divide-slate-100">
            {users.map((u) => (
              <div key={u.id} className="flex items-center justify-between gap-4 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">
                    {u.prenom} {u.nom}{" "}
                    {u.est_administrateur_systeme && (
                      <span className="ml-1 text-xs text-accent-600">· admin système</span>
                    )}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {u.email} · {u.poste_administratif}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Badge color={STATUT_BADGE[u.statut]}>{STATUT_LABEL[u.statut]}</Badge>
                  {u.statut !== "EN_ATTENTE" && !u.cle_publique_presente && (
                    <Badge color="red">Sans clé</Badge>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  {u.statut === "EN_ATTENTE" && (
                    <>
                      <Button variant="ghost" onClick={() => resendInvitation(u)}>
                        Renvoyer l'invitation
                      </Button>
                      <Button variant="danger" onClick={() => setConfirmingDelete(u)}>
                        Supprimer
                      </Button>
                    </>
                  )}
                  <Button variant="ghost" onClick={() => { setEditing(u); setFormError(""); }}>
                    Modifier
                  </Button>
                  {isAdmin && u.statut !== "EN_ATTENTE" && (
                    <Button
                      variant={u.statut === "ACTIF" ? "danger" : "primary"}
                      onClick={() =>
                        u.statut === "ACTIF" ? setConfirmingDeactivate(u) : doReactivate(u)
                      }
                    >
                      {u.statut === "ACTIF" ? "Désactiver" : "Réactiver"}
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm text-slate-600">
          <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ← Précédent
          </Button>
          <span>Page {page} / {totalPages}</span>
          <Button variant="ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Suivant →
          </Button>
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Créer un compte">
        <UserForm
          niveaux={niveaux}
          structures={structures}
          onSubmit={handleCreate}
          submitting={submitting}
          error={formError}
          isAdmin={isAdmin}
        />
      </Modal>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title="Modifier le compte">
        {editing && (
          <UserForm
            initial={editing}
            niveaux={niveaux}
            structures={structures}
            onSubmit={handleUpdate}
            submitting={submitting}
            error={formError}
            isAdmin={isAdmin}
          />
        )}
      </Modal>

      <Modal
        open={Boolean(confirmingDeactivate)}
        onClose={() => setConfirmingDeactivate(null)}
        title="Confirmer la désactivation"
      >
        {confirmingDeactivate && (
          <div className="space-y-4">
            <Alert type="warning">
              Le compte de <strong>{confirmingDeactivate.prenom} {confirmingDeactivate.nom}</strong>{" "}
              ({confirmingDeactivate.email}) sera immédiatement désactivé et sa session
              en cours (le cas échéant) sera invalidée sur-le-champ.
            </Alert>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmingDeactivate(null)}>Annuler</Button>
              <Button variant="danger" onClick={() => doDeactivate(confirmingDeactivate)}>
                Désactiver
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(confirmingDelete)}
        onClose={() => setConfirmingDelete(null)}
        title="Supprimer ce compte en attente"
      >
        {confirmingDelete && (
          <div className="space-y-4">
            <Alert type="warning">
              Le compte <strong>{confirmingDelete.email}</strong> n'a jamais été
              activé (aucune clé de chiffrement, aucun fichier associé). Il sera
              définitivement supprimé. Pour corriger une adresse mal saisie, préférez
              « Modifier » puis « Renvoyer l'invitation ».
            </Alert>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmingDelete(null)}>Annuler</Button>
              <Button variant="danger" onClick={() => doDelete(confirmingDelete)}>
                Supprimer définitivement
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
