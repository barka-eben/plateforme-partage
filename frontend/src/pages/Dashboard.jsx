import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import { downloadAndDecryptFile, triggerBrowserDownload } from "../services/fileTransfer";
import { useAuth } from "../context/AuthContext";
import { Card, CardHeader, EmptyState } from "../components/common/Card";
import { SentFileRow, ReceivedFileRow } from "../components/files/FileList";
import Alert from "../components/common/Alert";
import Spinner from "../components/common/Spinner";
import Button from "../components/common/Button";
import Modal from "../components/common/Modal";

export default function Dashboard() {
  const { privateKeyOAEP } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [envoyes, setEnvoyes] = useState([]);
  const [recus, setRecus] = useState([]);
  const [tab, setTab] = useState("recus");

  const [activeFile, setActiveFile] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [downloadDone, setDownloadDone] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.get("/files");
      setEnvoyes(data.envoyes);
      setRecus(data.recus);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openFile = (file) => {
    setActiveFile(file);
    setDownloadError("");
    setDownloadDone(false);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError("");
    try {
      const { blob, filename } = await downloadAndDecryptFile(activeFile.id, privateKeyOAEP);
      triggerBrowserDownload(blob, filename);
      setDownloadDone(true);
      load(); // rafraîchir les statuts de lecture
    } catch (err) {
      setDownloadError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  const nonLus = recus.filter((f) => !f.statut_lecture).length;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Tableau de bord</h1>
          <p className="mt-1 text-sm text-slate-500">
            Vos fichiers reçus et envoyés, chiffrés de bout en bout.
          </p>
        </div>
        <Link to="/envoyer">
          <Button>+ Envoyer un fichier</Button>
        </Link>
      </div>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <div className="mb-4 flex gap-2">
        <button
          onClick={() => setTab("recus")}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "recus" ? "bg-brand-700 text-white" : "bg-white text-slate-600 border border-slate-200"
          }`}
        >
          Reçus {nonLus > 0 && `(${nonLus} non lu${nonLus > 1 ? "s" : ""})`}
        </button>
        <button
          onClick={() => setTab("envoyes")}
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            tab === "envoyes" ? "bg-brand-700 text-white" : "bg-white text-slate-600 border border-slate-200"
          }`}
        >
          Envoyés
        </button>
      </div>

      <Card>
        {loading ? (
          <div className="flex justify-center py-14">
            <Spinner size={28} className="text-brand-600" />
          </div>
        ) : tab === "recus" ? (
          recus.length === 0 ? (
            <EmptyState icon="📥" title="Aucun fichier reçu" description="Les documents qui vous sont diffusés apparaîtront ici." />
          ) : (
            <div className="divide-y divide-slate-100">
              {recus.map((f) => (
                <ReceivedFileRow key={f.id} file={f} onOpen={openFile} />
              ))}
            </div>
          )
        ) : envoyes.length === 0 ? (
          <EmptyState icon="📤" title="Aucun fichier envoyé" description="Utilisez « Envoyer un fichier » pour diffuser un document." />
        ) : (
          <div className="divide-y divide-slate-100">
            {envoyes.map((f) => (
              <SentFileRow key={f.id} file={f} onOpen={openFile} />
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={Boolean(activeFile)}
        onClose={() => setActiveFile(null)}
        title={activeFile?.nom_chiffre}
      >
        {downloadDone ? (
          <Alert type="success">
            Signature vérifiée et fichier déchiffré avec succès. Le téléchargement a démarré.
          </Alert>
        ) : (
          <>
            <p className="mb-4 text-sm text-slate-600">
              Ce fichier va être téléchargé chiffré, puis la signature de son expéditeur sera
              vérifiée AVANT tout déchiffrement local.
            </p>
            {downloadError && <Alert type="error" className="mb-4">{downloadError}</Alert>}
            <Button onClick={handleDownload} loading={downloading} className="w-full">
              Vérifier &amp; déchiffrer
            </Button>
          </>
        )}
      </Modal>
    </div>
  );
}
