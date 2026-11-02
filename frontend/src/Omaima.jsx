// Petite décoration personnelle, demandée le 02/11/2026 pour Omaima (recherche de CDI en RH à Lyon).
// Visible seulement si le prénom du compte est Omaima (ou Oumaima) ET que la recherche est « cdi ».
const plain = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
export const isOmaima = me => /^ou?maima\b/.test(plain(me?.name));

function Sprig() {
  return (
    <svg className="om-sprig" viewBox="0 0 120 120" aria-hidden="true">
      <path d="M20 112 C40 80 52 56 92 22" fill="none" stroke="#3f7d5a" strokeWidth="3" strokeLinecap="round" />
      <path d="M44 78 C30 74 24 62 26 52 C38 56 46 66 44 78Z" fill="#7fb98f" />
      <path d="M58 60 C70 64 80 58 84 48 C72 44 62 50 58 60Z" fill="#7fb98f" />
      {[[92, 22, 11], [66, 40, 8], [38, 92, 7]].map(([x, y, r], i) => (
        <g key={i} transform={`translate(${x} ${y})`}>
          {[0, 72, 144, 216, 288].map(a => <ellipse key={a} rx={r * 0.55} ry={r} transform={`rotate(${a}) translate(0 ${-r * 0.8})`} fill={i === 1 ? "#ffb4c6" : "#ff8fab"} />)}
          <circle r={r * 0.45} fill="#ffd56b" />
        </g>
      ))}
    </svg>
  );
}

export default function OmaimaCard({ compact = false }) {
  return (
    <div className={"om-card" + (compact ? " compact" : "")} role="note">
      <Sprig />
      <div>
        <p className="om-hi">Bonne recherche, <span>Omaima</span> 🌷</p>
        {compact
          ? <p className="om-txt">Tes offres de CDI en RH autour de Lyon arrivent ici dès qu'elles sont trouvées.</p>
          : <p className="om-txt">Cet espace CDI a été préparé rien que pour toi : assistante RH, gestionnaire RH, paie et ADP, à Lyon et alentours. Les nouvelles offres arrivent toutes seules, il ne te reste qu'à choisir les meilleures.</p>}
      </div>
    </div>
  );
}
