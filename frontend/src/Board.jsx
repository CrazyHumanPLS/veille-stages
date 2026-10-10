import { useEffect, useState } from "react";
import { api } from "./api.jsx";

// Vitrine publique : les offres récentes d'un domaine, lisibles sans compte. Adresse : /#offres ou /#offres/data
const tone = s => (s >= 75 ? "hi" : s >= 55 ? "mid" : "lo");
const web = u => (/^https?:\/\//i.test(u || "") ? u : undefined);   // n'ouvre jamais autre chose qu'une adresse web
const when = d => {
  if (!d) return "";
  const days = Math.max(0, Math.round((Date.now() - new Date(d + "T12:00:00").getTime()) / 86400000));
  return days === 0 ? "mise en ligne aujourd'hui" : days === 1 ? "mise en ligne hier" : `mise en ligne il y a ${days} j`;
};

export default function Board({ info, domain, logged, onJoin }) {
  const [region, setRegion] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setErr("");
    api(`/api/public/offers?domain=${encodeURIComponent(domain || "")}&region=${encodeURIComponent(region)}`)
      .then(setData).catch(e => setErr(e.message));
  }, [domain, region]);
  useEffect(() => { if (data?.short) document.title = `Stages en ${data.short} | ${info?.name || "Veille Stages"}`; }, [data, info]);
  // Sur téléphone, la rangée de domaines défile : on amène le domaine affiché à l'écran.
  useEffect(() => { document.querySelector(".board .seg button.on")?.scrollIntoView({ block: "nearest", inline: "center" }); }, [data?.domain, info]);
  const name = info?.name || "Veille Stages";
  const domains = Object.entries(info?.domains || {});
  const more = data ? data.total - data.offers.length : 0;
  const cta = logged ? "Ouvrir mon tableau de bord" : "Créer mon compte gratuit";
  return (<div className="landing board">
    <div className="topbar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); onJoin(); }}><span className="mark" aria-hidden="true" />{name}</a>
      <button className="btn" onClick={onJoin}>{cta}</button>
    </div>
    <main className="wrap">
      <h1>{data ? <>Stages en {data.short}</> : "Les stages de la semaine"}</h1>
      <p className="lead">
        {data && data.total > 0
          ? <>{data.total} offre{data.total > 1 ? "s" : ""} repérée{data.total > 1 ? "s" : ""} cette semaine{data.fresh > 0 && <>, dont {data.fresh} ces dernières 48 heures</>}. Les sites carrières sont relevés en continu.</>
          : "Les sites carrières sont relevés en continu, partout en France."}
      </p>
      {domains.length > 0 && <div className="seg" role="tablist" aria-label="Domaine">
        {domains.map(([k, l]) => <button key={k} role="tab" aria-selected={data?.domain === k} className={data?.domain === k ? "on" : ""}
          onClick={() => { window.location.hash = `offres/${k}`; }}>{l.split(",")[0]}{data?.counts?.[k] ? ` (${data.counts[k]})` : ""}</button>)}
      </div>}
      <div className="filters">
        <select aria-label="Région" value={region} onChange={e => setRegion(e.target.value)}>
          <option value="">Toute la France</option>
          {Object.entries(info?.regions || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>
      {err && <p className="err">{err}</p>}
      {!data && !err && <p className="mute">Chargement… (jusqu'à une minute si le serveur dormait)</p>}
      {data && !data.offers.length && <div className="empty"><b>Aucune offre cette semaine dans cette sélection.</b><p className="mute">Essaie un autre domaine ou une autre région.</p></div>}
      {data?.offers.length > 0 && <div className="sheet">{data.offers.map(o => (
        <article className="offer" key={o.id}>
          <div className={`score ${tone(o.score)}`} title="Proximité avec le domaine, d'après les mots-clés de l'annonce"><span>{o.score}</span><small>mots-clés</small></div>
          <div className="body">
            <h2 className="otitle"><a href={web(o.url)} target="_blank" rel="noopener noreferrer nofollow">{o.title}</a></h2>
            <p className="ometa"><b>{o.company || "Entreprise non précisée"}</b><span>{o.place || "lieu non précisé"}</span><span>via {o.source}</span></p>
            {when(o.published) && <p className="odate">{when(o.published)}</p>}
            <div className="actions"><a className="btn ghost" href={web(o.url)} target="_blank" rel="noopener noreferrer nofollow">Voir l'offre</a></div>
          </div>
        </article>))}</div>}
      {data && <div className="card boardcta">
        <h2>{more > 0 ? `${more} autre${more > 1 ? "s" : ""} offre${more > 1 ? "s" : ""} cette semaine dans ce domaine` : "Ne rate pas les prochaines"}</h2>
        <p>Avec un compte, chaque offre est notée de 0 à 100 d'après ton CV, et les meilleures arrivent sur ton téléphone dès leur mise en ligne. Lettre de motivation et préparation d'entretien incluses.</p>
        <button className="btn big" onClick={onJoin}>{cta}</button>
        {!logged && <p className="mute">Gratuit, sans publicité.</p>}
      </div>}
      <footer className="mute"><a href="/stages">Tous les stages par domaine et par région</a></footer>
    </main>
  </div>);
}
