import { useEffect, useState, useCallback } from "react";
import { api } from "../../services/api";
import { Card, CardHeader, EmptyState } from "../../components/common/Card";
import Button from "../../components/common/Button";
import Input from "../../components/common/Input";
import Modal from "../../components/common/Modal";
import Alert from "../../components/common/Alert";
import Spinner from "../../components/common/Spinner";

export default function AdminNiveaux() {
  const [niveaux, setNiveaux] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ libelle: "", ordre: "" });
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/admin/niveaux");
      setNiveaux(data.niveaux);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm({ libelle: "", ordre: "" });
    setFormError("");
    setModalOpen(true);
  };

  const openEdit = (n) => {
    setEditing(n);
    setForm({ libelle: n.libelle, ordre: String(n.ordre) });
    setFormError("");
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError("");
    try {
      const payload = { libelle: form.libelle, ordre: Number(form.ordre) };
      if (editing) {
        await api.put(`/admin/niveaux/${editing.id}`, payload);
      } else {
        await api.post("/admin/niveaux", payload);
      }
      setModalOpen(false);
      load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (n) => {
    if (!window.confirm(`Supprimer le niveau "${n.libelle}" ?`)) return;
    try {
      await api.delete(`/admin/niveaux/${n.id}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Niveaux hiérarchiques</h1>
          <p className="mt-1 text-sm text-slate-500">
            Plus l'ordre est petit, plus le niveau est élevé dans la hiérarchie.
          </p>
        </div>
        <Button onClick={openCreate}>+ Nouveau niveau</Button>
      </div>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : niveaux.length === 0 ? (
          <EmptyState icon="📊" title="Aucun niveau défini" />
        ) : (
          <div className="divide-y divide-slate-100">
            {niveaux.map((n) => (
              <div key={n.id} className="flex items-center justify-between px-5 py-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                    {n.ordre}
                  </span>
                  <p className="text-sm font-medium text-slate-800">{n.libelle}</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={() => openEdit(n)}>
                    Modifier
                  </Button>
                  <Button variant="ghost" onClick={() => handleDelete(n)}>
                    Supprimer
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Modifier le niveau" : "Nouveau niveau"}
      >
        <form onSubmit={handleSubmit} className="space-y-3">
          {formError && <Alert type="error">{formError}</Alert>}
          <Input
            label="Libellé"
            required
            value={form.libelle}
            onChange={(e) => setForm({ ...form, libelle: e.target.value })}
            placeholder="Ex : Chef de service"
          />
          <Input
            label="Ordre (1 = le plus élevé)"
            type="number"
            required
            min="1"
            value={form.ordre}
            onChange={(e) => setForm({ ...form, ordre: e.target.value })}
          />
          <Button type="submit" loading={submitting} className="w-full">
            Enregistrer
          </Button>
        </form>
      </Modal>
    </div>
  );
}
