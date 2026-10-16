import { useEffect, useState, useCallback } from "react";
import { api } from "../../services/api";
import { Card, EmptyState } from "../../components/common/Card";
import Button from "../../components/common/Button";
import Input from "../../components/common/Input";
import Select from "../../components/common/Select";
import Modal from "../../components/common/Modal";
import Alert from "../../components/common/Alert";
import Spinner from "../../components/common/Spinner";

function TreeNode({ node, depth, onAddChild, onEdit, onDelete }) {
  return (
    <div>
      <div
        className="group flex items-center justify-between rounded-lg px-3 py-2 hover:bg-slate-50"
        style={{ marginLeft: depth * 20 }}
      >
        <div className="flex items-center gap-2">
          <span className="text-slate-400">{depth > 0 ? "└─" : "🏢"}</span>
          <span className="text-sm font-medium text-slate-800">{node.nom}</span>
        </div>
        <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <Button variant="ghost" onClick={() => onAddChild(node)}>
            + Unité
          </Button>
          <Button variant="ghost" onClick={() => onEdit(node)}>
            Modifier
          </Button>
          <Button variant="ghost" onClick={() => onDelete(node)}>
            Supprimer
          </Button>
        </div>
      </div>
      {node.enfants?.map((child) => (
        <TreeNode
          key={child.id}
          node={child}
          depth={depth + 1}
          onAddChild={onAddChild}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}

function flattenTree(nodes, depth = 0, acc = []) {
  for (const n of nodes) {
    acc.push({ id: n.id, nom: n.nom, depth });
    if (n.enfants?.length) flattenTree(n.enfants, depth + 1, acc);
  }
  return acc;
}

export default function AdminStructures() {
  const [tree, setTree] = useState([]);
  const [flatList, setFlatList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ nom: "", structure_parent_id: "" });
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get("/admin/structures/tree");
      setTree(data.arbre);
      setFlatList(flattenTree(data.arbre));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = (parent) => {
    setEditing(null);
    setForm({ nom: "", structure_parent_id: parent?.id || "" });
    setFormError("");
    setModalOpen(true);
  };

  const openEdit = (node) => {
    setEditing(node);
    setForm({ nom: node.nom, structure_parent_id: node.structure_parent_id || "" });
    setFormError("");
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError("");
    try {
      const payload = {
        nom: form.nom,
        structure_parent_id: form.structure_parent_id || null,
      };
      if (editing) {
        await api.put(`/admin/structures/${editing.id}`, payload);
      } else {
        await api.post("/admin/structures", payload);
      }
      setModalOpen(false);
      load();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (node) => {
    if (!window.confirm(`Supprimer l'unité "${node.nom}" ?`)) return;
    try {
      await api.delete(`/admin/structures/${node.id}`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Organigramme</h1>
          <p className="mt-1 text-sm text-slate-500">
            Arbre des directions, services et bureaux de l'administration.
          </p>
        </div>
        <Button onClick={() => openCreate(null)}>+ Nouvelle unité racine</Button>
      </div>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : tree.length === 0 ? (
          <EmptyState icon="🏢" title="Aucune structure définie" />
        ) : (
          <div className="px-2 py-3">
            {tree.map((node) => (
              <TreeNode
                key={node.id}
                node={node}
                depth={0}
                onAddChild={openCreate}
                onEdit={openEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Modifier l'unité" : "Nouvelle unité"}
      >
        <form onSubmit={handleSubmit} className="space-y-3">
          {formError && <Alert type="error">{formError}</Alert>}
          <Input
            label="Nom de l'unité"
            required
            value={form.nom}
            onChange={(e) => setForm({ ...form, nom: e.target.value })}
            placeholder="Ex : Service Développement"
          />
          <Select
            label="Unité parente"
            value={form.structure_parent_id}
            onChange={(e) => setForm({ ...form, structure_parent_id: e.target.value })}
          >
            <option value="">Aucune (racine)</option>
            {flatList
              .filter((s) => !editing || s.id !== editing.id)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {"— ".repeat(s.depth)}
                  {s.nom}
                </option>
              ))}
          </Select>
          <Button type="submit" loading={submitting} className="w-full">
            Enregistrer
          </Button>
        </form>
      </Modal>
    </div>
  );
}
