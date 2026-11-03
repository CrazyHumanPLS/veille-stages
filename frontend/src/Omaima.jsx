// Petite décoration personnelle, demandée le 02/11/2026 pour Omaima (recherche de CDI en RH à Lyon).
// Visible seulement si le prénom du compte est Omaima (ou Oumaima) ET que la recherche est « cdi ».
// Grande carte (Réglages) : poème + pluie de fleurs (une fois par visite, bouton pour la relancer).
import { useEffect, useMemo, useState } from "react";

const plain = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
export const isOmaima = me => /^ou?maima\b/.test(plain(me?.name));

const POEM = [
  ["Omaima, reine de la paie,", "devant toi la DSN se tait,", "ADP te fait la révérence", "et Excel te jure obéissance."],
  ["À Lyon, les CDI font la queue,", "se recoiffent, se font tout beaux,", "chacun rêve, les yeux pleins de feu,", "que tu choisisses son bureau."],
  ["Les bulletins sortent sans erreur,", "la machine à café t'applaudit,", "et le lundi, même à huit heures,", "on te verra sourire aussi."],
];

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

// Pluie de fleurs : 24 fleurs tombent une fois (environ 9 s), sans bloquer les clics, puis disparaissent.
function Rain({ onEnd }) {
  const flowers = useMemo(() => Array.from({ length: 24 }, (_, i) => ({
    left: Math.random() * 100, delay: Math.random() * 3, dur: 5 + Math.random() * 3,
    size: 16 + Math.random() * 16, sway: (Math.random() < .5 ? -1 : 1) * (20 + Math.random() * 50),
    glyph: ["🌸", "🌷", "🌺", "💮", "🌸"][i % 5],
  })), []);
  useEffect(() => { const t = setTimeout(onEnd, 9500); return () => clearTimeout(t); }, [onEnd]);
  return (
    <div className="om-rain" aria-hidden="true">
      {flowers.map((f, i) => <span key={i} style={{ left: `${f.left}%`, fontSize: f.size, animationDelay: `${f.delay}s`, animationDuration: `${f.dur}s`, "--sway": `${f.sway}px` }}>{f.glyph}</span>)}
    </div>
  );
}

const seen = () => { try { return sessionStorage.getItem("om-rain") === "1"; } catch { return false; } };
const markSeen = () => { try { sessionStorage.setItem("om-rain", "1"); } catch { /* sans stockage : la pluie revient, ce n'est pas grave */ } };

export default function OmaimaCard({ compact = false }) {
  const [rain, setRain] = useState(0);            // 0 = pas de pluie, sinon numéro de la pluie en cours
  useEffect(() => { if (!compact && !seen()) { markSeen(); setRain(1); } }, [compact]);
  const stop = useMemo(() => () => setRain(0), []);
  return (
    <div className={"om-card" + (compact ? " compact" : "")} role="note">
      {rain > 0 && <Rain key={rain} onEnd={stop} />}
      <Sprig />
      <div>
        <p className="om-hi">Bonne recherche, <span>Omaima</span> 🌷</p>
        {compact
          ? <p className="om-txt">Tes offres de CDI en RH autour de Lyon arrivent ici dès qu'elles sont trouvées.</p>
          : <>
              <p className="om-txt">Cet espace CDI a été préparé rien que pour toi. Un petit poème pour bien commencer :</p>
              <div className="om-poem">
                {POEM.map((s, i) => <p key={i}>{s.map((l, j) => <span key={j}>{l}<br /></span>)}</p>)}
                <p className="om-end">Alors fonce, l'avenir t'attend :<br />j'espère que tu vas être la meilleure des RH,<br />et surtout une <b>GENTILLE</b> RH 💗</p>
              </div>
              <button type="button" className="om-again" onClick={() => setRain(r => r + 1)}>🌸 Encore des fleurs</button>
            </>}
      </div>
    </div>
  );
}
