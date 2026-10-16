import Badge from "../common/Badge";

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SentFileRow({ file, onOpen }) {
  return (
    <button
      onClick={() => onOpen(file)}
      className="flex w-full items-center justify-between gap-4 px-5 py-3 text-left hover:bg-slate-50"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800">{file.nom_chiffre}</p>
        <p className="text-xs text-slate-500">Déposé le {formatDate(file.date_depot)}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge color="blue">{file.nb_destinataires} destinataire(s)</Badge>
        <Badge color={file.nb_lectures === file.nb_destinataires ? "green" : "amber"}>
          {file.nb_lectures}/{file.nb_destinataires} lu(s)
        </Badge>
      </div>
    </button>
  );
}

export function ReceivedFileRow({ file, onOpen }) {
  return (
    <button
      onClick={() => onOpen(file)}
      className="flex w-full items-center justify-between gap-4 px-5 py-3 text-left hover:bg-slate-50"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800">{file.nom_chiffre}</p>
        <p className="text-xs text-slate-500">
          De {file.expediteur_nom} · reçu le {formatDate(file.date_depot)}
        </p>
      </div>
      <div className="shrink-0">
        {file.statut_lecture ? (
          <Badge color="gray">Déjà ouvert</Badge>
        ) : (
          <Badge color="blue">Nouveau</Badge>
        )}
      </div>
    </button>
  );
}
