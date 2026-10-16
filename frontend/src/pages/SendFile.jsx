import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { sendFile } from "../services/fileTransfer";
import { Card, CardHeader } from "../components/common/Card";
import RecipientPicker from "../components/files/RecipientPicker";
import Alert from "../components/common/Alert";
import Button from "../components/common/Button";
import ProgressBar from "../components/common/ProgressBar";

const MAX_FILE_SIZE_MB = 50;

export default function SendFile() {
  const { privateKeyPSS, publicKeyOAEP } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [destinataires, setDestinataires] = useState([]);
  const [diffusionMeta, setDiffusionMeta] = useState({ mode: "user" });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState({ label: "", current: 0, total: 1 });
  const [success, setSuccess] = useState(null);

  const handleFileChange = (e) => {
    setError("");
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setError(`Le fichier dépasse la taille maximale autorisée (${MAX_FILE_SIZE_MB} Mo).`);
      return;
    }
    setFile(f);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!file) {
      setError("Sélectionnez un fichier à envoyer.");
      return;
    }
    if (destinataires.length === 0) {
      setError("Sélectionnez au moins un destinataire.");
      return;
    }

    setSending(true);
    setProgress({ label: "Préparation", current: 0, total: 1 });

    try {
      const result = await sendFile(
        file,
        destinataires,
        privateKeyPSS,
        publicKeyOAEP,
        (label, current, total) => setProgress({ label, current, total }),
        diffusionMeta
      );
      setSuccess(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  if (success) {
    return (
      <div className="mx-auto max-w-lg">
        <Card>
          <div className="px-6 py-10 text-center">
            <span className="mb-3 block text-4xl">✅</span>
            <h2 className="text-lg font-semibold text-slate-900">Fichier envoyé avec succès</h2>
            <p className="mt-2 text-sm text-slate-500">
              Diffusé de manière chiffrée à {success.nombre_destinataires} destinataire(s).
            </p>
            {success.destinatairesIgnores?.length > 0 && (
              <p className="mt-2 text-xs text-amber-600">
                {success.destinatairesIgnores.length} destinataire(s) ignoré(s)
                (compte pas encore activé).
              </p>
            )}
            <div className="mt-6 flex justify-center gap-3">
              <Button variant="secondary" onClick={() => navigate("/")}>
                Retour au tableau de bord
              </Button>
              <Button
                onClick={() => {
                  setSuccess(null);
                  setFile(null);
                  setDestinataires([]);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
              >
                Envoyer un autre fichier
              </Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-1 text-xl font-bold text-slate-900">Envoyer un fichier</h1>
      <p className="mb-6 text-sm text-slate-500">
        Le fichier est chiffré, haché et signé entièrement dans votre navigateur avant
        tout envoi. Le serveur ne voit jamais son contenu en clair.
      </p>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader title="1. Destinataires" />
          <div className="px-5 py-4">
            <RecipientPicker
              onResolved={(dests, meta) => {
                setDestinataires(dests);
                if (meta) setDiffusionMeta(meta);
              }}
            />
          </div>
        </Card>

        <Card>
          <CardHeader title="2. Fichier" />
          <div className="px-5 py-4">
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileChange}
              className="block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
            />
            {file && (
              <p className="mt-2 text-xs text-slate-500">
                {file.name} · {(file.size / 1024).toFixed(1)} Ko
              </p>
            )}
            <p className="mt-2 text-xs text-slate-400">Taille maximale : {MAX_FILE_SIZE_MB} Mo</p>
          </div>
        </Card>

        {error && <Alert type="error">{error}</Alert>}

        {sending && (
          <Card>
            <div className="px-5 py-4">
              <ProgressBar value={progress.current} max={progress.total} label={progress.label} />
            </div>
          </Card>
        )}

        <Button type="submit" loading={sending} className="w-full" disabled={sending}>
          Chiffrer, signer et envoyer
        </Button>
      </form>
    </div>
  );
}
