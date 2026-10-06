import { useCallback, useEffect, useRef, useState } from "react";
import { api, post, put, ago, Dot, List, getToken, setToken, setOnLogout, useAction } from "./api.jsx";
import Settings from "./Settings.jsx";
import Admin from "./Admin.jsx";
import * as audience from "./analytics.js";

const STATUS = ["À postuler", "Postulé", "Relancé", "Entretien", "Offre", "Refus"];
const TASKS = { fit: "Analyser l'offre", letter: "Écrire ma lettre", cv: "Adapter mon CV", message: "Message au recruteur", interview: "Simuler l'entretien", targets: "Trouver des cibles" };
const best = o => (o.ai_score ?? o.kw_score);
const pubLabel = d => {
  if (!d) return "date de mise en ligne inconnue";
  const days = Math.max(0, Math.round((Date.now() - new Date(d + "T12:00:00").getTime()) / 86400000));
  const rel = days === 0 ? "aujourd'hui" : days === 1 ? "hier" : `il y a ${days} j`;
  return `mise en ligne le ${d.slice(8, 10)}/${d.slice(5, 7)} (${rel})`;
};
const tone = s => (s >= 75 ? "hi" : s >= 55 ? "mid" : "lo");
const web = u => (/^https?:\/\//i.test(u || "") ? u : undefined);   // n'ouvre jamais autre chose qu'une adresse web

function Privacy({ info }) {
  return (<div className="card privacy">
    <h3>Tes données, en clair</h3>
    <ul>
      <li><b>Ce qui est enregistré :</b> ton adresse e-mail, ton mot de passe (sous forme chiffrée, illisible), le texte de tes CV, tes réglages, tes candidatures et le tri de tes offres.</li>
      <li><b>À quoi ça sert :</b> uniquement à te proposer des offres, à les noter d'après ton CV et à t'envoyer tes alertes. Rien n'est vendu ni transmis à des recruteurs.</li>
      <li><b>Intelligence artificielle :</b> pour noter les offres et rédiger tes lettres, le texte de ton CV et de l'offre est envoyé à Google Gemini. Avec une clé gratuite, Google peut utiliser ces textes pour améliorer ses services : retire de ton CV ce que tu ne veux pas partager (adresse postale, téléphone).</li>
      <li><b>Secrets :</b> ta clé Gemini et tes adresses d'alerte sont chiffrées dans la base et ne sont jamais réaffichées.</li>
      <li><b>Tes droits :</b> tu peux télécharger toutes tes données et supprimer ton compte à tout moment, depuis l'onglet Réglages. La suppression est immédiate et définitive.</li>
      <li><b>Comptes inactifs :</b> sans visite pendant 3 semaines, ta veille se met en pause ; elle reprend dès que tu te reconnectes.</li>
      {info?.ga
        ? <li><b>Cookies :</b> aucun cookie publicitaire. Si tu l'acceptes, Google Analytics dépose des cookies pour compter les visites et les écrans consultés ; ni ton CV, ni ton adresse e-mail, ni tes offres ne lui sont envoyés. Tu peux changer d'avis à tout moment avec le lien « Cookies » en bas de page.</li>
        : <li><b>Cookies :</b> aucun cookie publicitaire ni traceur. Seule ta connexion est gardée dans ton navigateur.</li>}
    </ul>
    {info?.contact && <p className="mute">Une question sur tes données : {info.contact}</p>}
  </div>);
}

// Bandeau de consentement : n'existe que si le site mesure son audience. Refuser est aussi simple qu'accepter.
function Consent({ info, ask, onDone, onMore }) {
  if (!info?.ga || !ask) return null;
  return (<div className="consent" role="dialog" aria-label="Mesure d'audience">
    <p>Pour savoir combien de personnes utilisent le site, on aimerait mesurer son audience avec Google Analytics, qui dépose des cookies. Tu peux refuser : le site fonctionne exactement pareil. <a href="#" onClick={e => { e.preventDefault(); onMore(); }}>En savoir plus</a></p>
    <div className="row">
      <button className="btn ghost" onClick={() => { audience.refuse(); onDone(); }}>Refuser</button>
      <button className="btn" onClick={() => { audience.accept(info.ga); onDone(); }}>Accepter</button>
    </div>
  </div>);
}

function Terms({ info }) {
  const paid = /^https:\/\//.test(info?.premium?.url || "");
  return (<div className="card privacy">
    <h3>Conditions d'utilisation</h3>
    <ul>
      <li><b>Le service :</b> {info?.name || "Veille Stages"} collecte des offres de stage en France publiées sur des sites d'entreprises et des agrégateurs, les trie selon ton profil et t'aide à préparer tes candidatures.</li>
      <li><b>Ton compte :</b> une personne, un compte. Tu es responsable de ton mot de passe et de l'exactitude de ce que tu importes. Un compte utilisé pour surcharger le service ou nuire à d'autres personnes peut être désactivé.</li>
      <li><b>Les offres :</b> elles appartiennent aux entreprises qui les publient. Une offre peut être expirée, modifiée ou erronée : vérifie toujours sur le site de l'entreprise avant de postuler.</li>
      <li><b>L'intelligence artificielle :</b> les notes, analyses et lettres sont produites automatiquement. Elles peuvent contenir des erreurs : relis toujours un texte avant de l'envoyer. Le service ne garantit ni entretien ni embauche.</li>
      <li><b>Disponibilité :</b> le service est fourni tel quel, sans garantie de fonctionnement continu. Des interruptions et des évolutions sont possibles.</li>
      {paid && <li><b>Formule Premium :</b> elle relève tes limites d'usage pour la durée indiquée lors du paiement. Elle est activée à la main après paiement. Tu peux demander son remboursement dans les 14 jours qui suivent le paiement, en écrivant à l'adresse de contact.</li>}
      <li><b>Arrêt :</b> tu peux supprimer ton compte à tout moment depuis l'onglet Réglages. Toutes tes données sont alors effacées.</li>
      <li><b>Droit applicable :</b> droit français.</li>
    </ul>
  </div>);
}

function Imprint({ info }) {
  return (<div className="card privacy">
    <h3>Mentions légales</h3>
    <ul>
      <li><b>Éditeur :</b> {info?.owner || "site édité à titre personnel par un particulier"}.</li>
      {info?.contact && <li><b>Contact :</b> {info.contact}</li>}
      <li><b>Hébergement du site :</b> Render Services, Inc., San Francisco, États-Unis (render.com).</li>
      <li><b>Hébergement de la base de données :</b> Supabase, Inc. (supabase.com).</li>
    </ul>
  </div>);
}

const Legal = ({ info, only }) => (<>
  {(!only || only === "terms") && <Terms info={info} />}
  {(!only || only === "privacy") && <Privacy info={info} />}
  {(!only || only === "imprint") && <Imprint info={info} />}
</>);

// Rappel tant que l'adresse e-mail n'est pas confirmée.
function Unverified({ me }) {
  const { msg, busy, act } = useAction();
  if (me.verified) return null;
  return (<div className="note verify">
    <p><b>Confirme ton adresse e-mail.</b> Un message a été envoyé à {me.email}. Clique sur le lien qu'il contient pour que tes offres soient notées par l'IA. Pense à regarder dans tes indésirables.</p>
    <button className="btn ghost" disabled={busy} onClick={() => act("Envoi…", async () => { await post("/api/me/verify/resend"); return "E-mail renvoyé."; })}>Renvoyer l'e-mail</button>
    {msg && <span className="mute">{msg}</span>}
  </div>);
}

// Premiers pas : deux réglages à faire une fois, dans l'ordre.
function Start({ me, go }) {
  const alerts = me.alerts.discord || me.alerts.ntfy || me.alerts.telegram;
  const chosen = me.settings?.search_set;
  if (me.cv && alerts && chosen) return null;
  const steps = [
    [!!chosen, "Choisis ton domaine et ta région", "Réseaux, embarqué, développement, data, industrie, gestion : partout en France ou dans tes régions.", "settings", "Régler ma recherche"],
    [!!me.cv, "Importe ton CV", "Un PDF suffit. Chaque offre est ensuite notée d'après ton profil.", "profile", "Importer mon CV"],
    [!!alerts, "Branche tes alertes", "Les bonnes offres arrivent sur ton téléphone dès leur mise en ligne.", "settings", "Brancher mes alertes"],
  ];
  return (<section className="start">
    <h2>Bienvenue{me.name ? ` ${me.name}` : ""}. Trois réglages et c'est parti.</h2>
    <ol>{steps.map(([done, title, text, tab, label]) => (
      <li key={label} className={done ? "done" : ""}>
        <div><b>{title}</b><span>{text}</span></div>
        {done ? <em>Fait</em> : <button className="btn" onClick={() => go(tab)}>{label}</button>}
      </li>))}</ol>
  </section>);
}

const Mark = () => <span className="mark" aria-hidden="true" />;
const ICONS = {
  feed: "M4 6h16M4 12h16M4 18h10", track: "M5 12l4 4 10-10", ai: "M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z",
  profile: "M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0", settings: "M4 7h10M18 7h2M4 17h2M10 17h10M16 4v6M8 14v6",
};
const Icon = ({ name }) => <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[name]} /></svg>;

function Score({ o }) {
  const s = best(o);
  return (<div className={`score ${tone(s)}`} title={o.ai_score == null ? "Score par mots-clés" : "Score de l'IA d'après ton CV"}>
    <span>{s}</span>{o.ai_score == null && <small>mots-clés</small>}
  </div>);
}

// Aperçu du produit sur la page d'accueil : exemples inventés, pas de vraies offres.
const DEMO = [
  { s: 92, t: "Stage ingénieur réseaux et sécurité", c: "Nordlink", p: "Massy", w: "Ton projet BGP et ton expérience Cisco couvrent l'essentiel de la mission." },
  { s: 78, t: "Stagiaire analyste SOC", c: "Atelier Cyber", p: "Paris 9e", w: "Bon niveau attendu en SIEM, il te manque la partie EDR." },
  { s: 61, t: "Stage DevOps plateforme", c: "Lumen Cloud", p: "Nanterre", w: "Domaine voisin : Kubernetes demandé, peu présent dans ton CV." },
];

function NewPassword({ info, token, onOk, onCancel }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async e => {
    e.preventDefault(); setErr(""); setBusy(true);
    try { const r = await post("/api/password/reset", { token, new: pw }); setToken(r.token); onOk(r.me); }
    catch (x) { setErr(x.message); }
    setBusy(false);
  };
  return (<div className="landing">
    <div className="topbar"><div className="brand"><Mark />{info?.name || "Veille Stages"}</div></div>
    <div className="wrap narrow">
      <h2>Choisis ton nouveau mot de passe</h2>
      <form className="join form" onSubmit={go}>
        <label>Nouveau mot de passe (8 caractères minimum)<input type="password" required minLength={8} autoFocus value={pw} onChange={e => setPw(e.target.value)} autoComplete="new-password" /></label>
        <button className="btn big" disabled={busy}>{busy ? "Un instant…" : "Enregistrer et me connecter"}</button>
        {err && <p className="err">{err}</p>}
        <p className="mute"><a href="#" onClick={e => { e.preventDefault(); onCancel(); }}>Revenir à l'accueil</a></p>
      </form>
    </div>
  </div>);
}

function Auth({ info, onOk, onCookies }) {
  const closed = info?.signup === "closed";
  const [mode, setMode] = useState("signup");
  const [f, setF] = useState({ email: "", password: "", name: "", invite: "", consent: false });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [doc, setDoc] = useState("");   // page légale ouverte : "", "terms", "privacy" ou "imprint"
  const open = k => e => { e.preventDefault(); setDoc(doc === k ? "" : k); setTimeout(() => document.getElementById("legal")?.scrollIntoView({ behavior: "smooth" }), 50); };
  const set = k => e => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const [sent, setSent] = useState(false);
  const go = async e => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      if (mode === "forgot") { await post("/api/password/forgot", { email: f.email }); setSent(true); }
      else { const r = await post(mode === "login" ? "/api/login" : "/api/signup", f); setToken(r.token); onOk(r.me); }
    } catch (x) { setErr(x.message); }
    setBusy(false);
  };
  const lim = info?.limits;
  return (<div className="landing">
    <div className="topbar"><div className="brand"><Mark />{info?.name || "Veille Stages"}</div></div>
    <main className="hero">
      <section className="pitch">
        <h1>Arrête de chercher. Les bons stages arrivent tout seuls.</h1>
        <p className="lead">On surveille les sites carrières jour et nuit. Chaque offre est notée d'après ton CV, et les meilleures arrivent sur ton téléphone dès leur mise en ligne.</p>
        <div className="demo" aria-hidden="true">
          <div className="ping"><b>Nouvelle offre, 92 sur 100</b><span>Stage ingénieur réseaux et sécurité, à l'instant</span></div>
          <div className="sheet">{DEMO.map(d => (
            <div className="offer" key={d.t}>
              <div className={`score ${tone(d.s)}`}><span>{d.s}</span></div>
              <div className="body"><div className="otitle">{d.t}</div><p className="ometa"><b>{d.c}</b><span>{d.p}</span></p><p className="why">{d.w}</p></div>
            </div>))}</div>
        </div>
      </section>
      <section className="join">
        <div className="tabs2" role="tablist">
          <button role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "on" : ""} onClick={() => { setMode("signup"); setErr(""); }}>Créer un compte</button>
          <button role="tab" aria-selected={mode === "login"} className={mode !== "signup" ? "on" : ""} onClick={() => { setMode("login"); setErr(""); }}>Se connecter</button>
        </div>
        {mode === "forgot" ? (sent
          ? <div className="form"><p className="note">Si un compte existe avec cette adresse, un e-mail vient de partir. Le lien est valable une heure. Pense à regarder dans tes indésirables.</p>
              <button className="btn ghost" onClick={() => { setMode("login"); setSent(false); }}>Revenir à la connexion</button></div>
          : <form className="form" onSubmit={go}>
              <p className="mute">Indique l'adresse de ton compte : tu recevras un lien pour choisir un nouveau mot de passe.</p>
              <label>Adresse e-mail<input type="email" required autoFocus value={f.email} onChange={set("email")} autoComplete="email" /></label>
              <button className="btn big" disabled={busy}>{busy ? "Un instant…" : "Recevoir le lien"}</button>
              {err && <p className="err">{err}</p>}
              <p className="mute"><a href="#" onClick={e => { e.preventDefault(); setMode("login"); setErr(""); }}>Revenir à la connexion</a></p>
            </form>) :
        mode === "signup" && closed ? <p className="note">Les inscriptions sont fermées pour le moment.</p> :
          <form className="form" onSubmit={go}>
            {mode === "signup" && <label>Prénom<input value={f.name} onChange={set("name")} maxLength={80} autoComplete="given-name" /></label>}
            <label>Adresse e-mail<input type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></label>
            <label>Mot de passe{mode === "signup" && " (8 caractères minimum)"}<input type="password" required minLength={mode === "signup" ? 8 : 1} value={f.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
            {mode === "signup" && info?.signup === "invite" && <label>Code d'invitation<input required value={f.invite} onChange={set("invite")} /></label>}
            {mode === "signup" && <label className="check"><input type="checkbox" checked={f.consent} onChange={set("consent")} />
              <span>J'accepte les <a href="#" onClick={open("terms")}>conditions d'utilisation</a> et que mon CV soit enregistré et analysé pour me proposer des offres (<a href="#" onClick={open("privacy")}>détail</a>).</span></label>}
            <button className="btn big" disabled={busy}>{busy ? "Un instant…" : mode === "login" ? "Se connecter" : "Créer mon compte gratuit"}</button>
            {err && <p className="err">{err}</p>}
            {mode === "login" && (info?.mail
              ? <p className="mute"><a href="#" onClick={e => { e.preventDefault(); setMode("forgot"); setErr(""); setSent(false); }}>Mot de passe oublié ?</a></p>
              : <p className="mute">Mot de passe oublié ? Demande à la personne qui t'a donné l'adresse du site : elle peut t'en créer un nouveau.</p>)}
          </form>}
        {mode === "signup" && !closed && <ul className="perks">
          <li>Gratuit, sans publicité.</li>
          {lim && info.shared_ai && <li>IA incluse : {lim.score} offres notées et {lim.assist} lettres ou analyses par jour.</li>}
          <li>Sans limite avec ta propre clé Gemini, gratuite elle aussi.</li>
        </ul>}
      </section>
    </main>
    <section className="steps wrap">
      <h2>Comment ça marche</h2>
      <ol>
        <li><b>Tu choisis ton domaine et tu importes ton CV.</b> Réseaux, cybersécurité, embarqué, électronique, développement, data, industrie, gestion. Un PDF suffit.</li>
        <li><b>On surveille pour toi.</b> Les nouvelles offres de stage, partout en France et dans ton domaine, sont collectées en continu et notées de 0 à 100.</li>
        <li><b>Tu reçois une alerte.</b> Dès qu'une offre dépasse ton seuil, elle arrive sur ton téléphone, avec le CV à envoyer.</li>
        <li><b>Tu postules plus vite.</b> Lettre, message au recruteur et préparation d'entretien se rédigent à partir de l'offre et de ton CV.</li>
      </ol>
    </section>
    <div className="wrap" id="legal">
      {doc && <Legal info={info} only={doc} />}
      <footer className="mute">
        <a href="#" onClick={open("terms")}>Conditions d'utilisation</a>
        <a href="#" onClick={open("privacy")}>Confidentialité</a>
        <a href="#" onClick={open("imprint")}>Mentions légales</a>
        {info?.ga && <a href="#" onClick={e => { e.preventDefault(); onCookies(); }}>Cookies</a>}
      </footer>
    </div>
  </div>);
}

const STATES = [["new", "Nouvelles"], ["saved", "Gardées"], ["applied", "Postulées"], ["hidden", "Masquées"], ["all", "Toutes"]];
const STATE_DONE = { saved: "Offre gardée", hidden: "Offre masquée", applied: "Candidature notée dans le suivi", new: "Offre remise dans les nouvelles" };

function Feed({ me, onTrack, onUntrack, onAnalyse, status, refreshStatus, reloadKey, focusId, toast }) {
  const [list, setList] = useState(null);
  const [f, setF] = useState({ state: "new", min: 0, q: "", hours: 0 });
  const [sort, setSort] = useState("seen");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const load = useCallback(() => {
    api(`/api/offers?state=${f.state}&min_score=${f.min}&hours=${f.hours}&q=${encodeURIComponent(f.q)}`)
      .then(l => { setList(l); setErr(""); }).catch(e => setErr(e.message));
  }, [f]);
  useEffect(() => { load(); const t = setInterval(() => { load(); refreshStatus(); }, 60000); return () => clearInterval(t); }, [load, reloadKey]);
  const patch = (id, state) => api(`/api/offers/${id}`, { method: "PATCH", body: JSON.stringify({ state }) });
  // L'offre quitte la liste tout de suite ; le message propose d'annuler pendant quelques secondes.
  const setState = async (o, state, alsoUndo) => {
    const before = o.state;
    setList(l => l && (f.state === "all" ? l.map(x => x.id === o.id ? { ...x, state } : x) : l.filter(x => x.id !== o.id)));
    try { await patch(o.id, state); toast(STATE_DONE[state], async () => { await patch(o.id, before); if (alsoUndo) await alsoUndo(); load(); refreshStatus(); }); }
    catch (e) { setErr(e.message); load(); }
    refreshStatus();
  };
  const refresh = async () => {
    setBusy(true); setNote(""); setErr("");
    try {
      const r = await post("/api/refresh");
      setNote(r.setup === "email" ? "Confirme ton adresse e-mail pour que tes offres soient notées par l'IA."
        : r.setup ? "Importe ton CV dans l'onglet Profil : tes offres seront notées et tes alertes activées."
        : r.waiting ? `Notation en cours : ${r.scored} offre(s) notée(s), la suite arrive dans quelques minutes.`
        : `À jour : ${r.new} nouvelle(s) offre(s) pour toi, ${r.scored} notée(s) par l'IA, ${r.alerts} alerte(s) envoyée(s).`);
    } catch (e) { setErr(e.message); }
    setBusy(false); load(); refreshStatus();
  };
  const analyse = async o => { const full = await api(`/api/offers/${o.id}`); onAnalyse(`${full.title}\n${full.company} · ${full.place}\n\n${full.description}`, full.cv || "", { id: o.id, title: o.title, company: o.company, url: o.url, state: o.state }); };
  const run = status?.last_run;
  const sorted = list && [...list].sort((a, b) => sort === "score" ? best(b) - best(a)
    : sort === "pub" ? (b.published || "0").localeCompare(a.published || "0") : b.first_seen - a.first_seen);
  return (<>
    <div className="summary">
      <p><b>{status?.last_24h ?? "…"}</b> nouvelles depuis 24 h, <b>{status?.total ?? "…"}</b> offres pour toi. <span className="mute">Dernière collecte {run ? ago(run.at) : "jamais"}.</span></p>
      <button className="btn ghost" onClick={refresh} disabled={busy}>{busy ? "Mise à jour…" : "Actualiser"}</button>
    </div>
    <div className="seg" role="tablist" aria-label="Filtrer par état">
      {STATES.map(([k, l]) => <button key={k} role="tab" aria-selected={f.state === k} className={f.state === k ? "on" : ""} onClick={() => setF({ ...f, state: k })}>{l}</button>)}
    </div>
    <div className="filters">
      <input type="search" value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Chercher une entreprise…" />
      <select aria-label="Score minimal" value={f.min} onChange={e => setF({ ...f, min: +e.target.value })}>
        <option value={0}>Tous les scores</option><option value={55}>55 et plus</option><option value={75}>75 et plus</option></select>
      <select aria-label="Période" value={f.hours} onChange={e => setF({ ...f, hours: +e.target.value })}>
        <option value={0}>Toutes dates</option><option value={2}>2 dernières heures</option><option value={24}>24 h</option><option value={72}>3 jours</option></select>
      <select aria-label="Tri" value={sort} onChange={e => setSort(e.target.value)}>
        <option value="seen">Les plus récentes</option><option value="pub">Mises en ligne récemment</option><option value="score">Meilleur score</option></select>
    </div>
    {note && <p className="note">{note}</p>}
    {err && <p className="err">{err}</p>}
    {!list && !err && <div className="sheet" aria-busy="true">{[0, 1, 2, 3].map(i => <div className="offer skeleton" key={i}><div className="sk sk-score" /><div className="body"><div className="sk sk-1" /><div className="sk sk-2" /><div className="sk sk-3" /></div></div>)}</div>}
    {list && !list.length && <div className="empty"><b>Rien dans cette liste pour l'instant.</b><p className="mute">{f.state === "new" ? "La collecte tourne en continu : les nouvelles offres apparaîtront ici. Tes mots-clés se règlent dans l'onglet Réglages." : "Change de filtre ci-dessus pour voir tes autres offres."}</p></div>}
    {sorted?.length > 0 && <div className="sheet">{sorted.map(o => (
      <article className={`offer${focusId === o.id ? " focus" : ""}`} key={o.id} id={`offer-${o.id}`}>
        <Score o={o} />
        <div className="body">
          <h2 className="otitle"><a href={web(o.url)} target="_blank" rel="noopener noreferrer">{o.title}</a></h2>
          <p className="ometa"><b>{o.company || "Entreprise non précisée"}</b><span>{o.place || "lieu non précisé"}</span><span>via {o.source}</span></p>
          {o.ai_reason ? <p className="why">{o.ai_reason}</p> : o.excerpt && <p className="excerpt">{o.excerpt.slice(0, 200)}…</p>}
          {me.cv > 1 && o.cv && <span className="tag">CV à envoyer : {me.cv_labels?.[o.cv] || o.cv}</span>}
          {o.dup_note && <p className="warn">{o.dup_note}</p>}
          <p className="odate">{pubLabel(o.published)}, détectée {ago(o.first_seen)}</p>
          <div className="actions">
            <a className="btn" href={web(o.url)} target="_blank" rel="noopener noreferrer">Voir l'offre</a>
            <button className="btn ghost" onClick={() => analyse(o)}>Lettre et analyse</button>
            {o.state !== "applied" && <button className="btn ghost" onClick={async () => { const id = await onTrack({ company: o.company, job: o.title, url: o.url, status: 1 }); setState(o, "applied", () => onUntrack(id)); }}>J'ai postulé</button>}
            {o.state !== "saved" && o.state !== "applied" && <button className="btn ghost" onClick={() => setState(o, "saved")}>Garder</button>}
            {o.state !== "hidden" ? <button className="btn quiet" onClick={() => setState(o, "hidden")}>Masquer</button>
              : <button className="btn quiet" onClick={() => setState(o, "new")}>Remettre</button>}
          </div>
        </div>
      </article>))}</div>}
  </>);
}

function Tracker({ apps, reload }) {
  const [f, setF] = useState({ company: "", job: "", url: "" });
  const add = async () => {
    if (!f.company.trim()) return;
    await post("/api/applications", { ...f, status: 1 });
    setF({ company: "", job: "", url: "" }); reload();
  };
  const sent = apps.filter(a => a.status >= 1).length;
  const late = a => (a.status === 1 || a.status === 2) && (Date.now() / 1000 - a.updated) / 86400 >= 7;
  return (<>
    <div className="summary"><p><b>{sent}</b> candidature(s) envoyée(s), <b>{apps.filter(late).length}</b> à relancer.</p></div>
    <div className="row">
      {["company", "job", "url"].map(k => <input key={k} value={f[k]} placeholder={{ company: "Entreprise", job: "Poste", url: "Lien" }[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}
      <button className="btn" onClick={add}>Ajouter (postulé)</button>
    </div>
    <div className="card scroll"><table>
      <thead><tr><th>Entreprise</th><th>Poste</th><th>Statut</th><th></th></tr></thead>
      <tbody>{apps.map(a => (
        <tr key={a.id}>
          <td>{a.company}</td>
          <td>{/^https?:\/\//.test(a.url || "") ? <a href={a.url} target="_blank" rel="noopener noreferrer">{a.job || "lien"}</a> : a.job}{late(a) && <div className="err">À relancer (7 jours sans nouvelles)</div>}</td>
          <td><select value={a.status} onChange={async e => { await api(`/api/applications/${a.id}?status=${e.target.value}`, { method: "PATCH" }); reload(); }}>
            {STATUS.map((s, i) => <option key={i} value={i}>{s}</option>)}</select></td>
          <td><button className="btn ghost" onClick={async () => { await api(`/api/applications/${a.id}`, { method: "DELETE" }); reload(); }}>Supprimer</button></td>
        </tr>))}</tbody>
    </table>{!apps.length && <p className="mute">Aucune candidature pour l'instant.</p>}</div>
  </>);
}

export function Quota({ ai, kind, what, goSettings }) {
  if (!ai) return null;
  const k = ai.kinds[kind];
  if (ai.own_key) return <p className="mute">Tu utilises ta propre clé Gemini : pas de limite côté site.</p>;
  if (!ai.shared_available) return <p className="note">L'IA n'est pas incluse sur ce site pour l'instant. <a href="#" onClick={goSettings}>Ajoute ta clé Gemini gratuite</a> pour l'activer.</p>;
  const left = Math.max(0, k.limit - k.used);
  return <p className={left ? "mute" : "note"}>{left ? `Il te reste ${left} ${what} aujourd'hui sur ${k.limit}.` : `Limite du jour atteinte (${k.limit} ${what}). Retour à zéro à minuit.`} <a href="#" onClick={goSettings}>Passer en illimité avec ta propre clé gratuite</a></p>;
}

function Assistant({ me, setMe, offer, setOffer, cv, setCv, goSettings, ctx, onBack, onState }) {
  const [out, setOut] = useState("Choisis une action. Le CV sélectionné ci-dessous est utilisé comme base.");
  const [busy, setBusy] = useState(false);
  const run = async task => {
    if (["fit", "letter", "cv", "message"].includes(task) && !offer.trim()) return setOut("Colle d'abord le texte de l'offre (ou clique « Lettre et analyse » sur une offre).");
    setBusy(true); setOut("L'IA réfléchit…");
    try { const r = await post("/api/ai", { task, offer, cv }); setOut(r.text); setMe({ ...me, ai: { ...me.ai, ...r.ai } }); }
    catch (e) { setOut("Erreur : " + e.message); }
    setBusy(false);
  };
  const mine = Object.entries(me.cv_labels || {}).filter(([k]) => me.cv_slots?.includes(k));
  return (<>
    <div className="row"><button className="btn ghost" onClick={onBack}>← Retour aux offres</button></div>
    {ctx && <div className="card ctx">
      <div><strong>{ctx.title}</strong><div className="mute">{ctx.company || "Entreprise non précisée"}{ctx.state === "saved" && " · gardée"}{ctx.state === "applied" && " · postulée"}</div></div>
      <div className="row">
        <a className="btn" href={web(ctx.url)} target="_blank" rel="noopener noreferrer">Voir l'offre</a>
        {ctx.state !== "saved" && ctx.state !== "applied" && <button className="btn ghost" onClick={() => onState("saved")}>Garder</button>}
        {ctx.state !== "applied" && <button className="btn ghost" onClick={() => onState("applied")}>J'ai postulé</button>}
      </div>
    </div>}
    <Quota ai={me.ai} kind="assist" what="générations" goSettings={goSettings} />
    {mine.length > 1 && <div className="row"><label>CV utilisé <select value={cv} onChange={e => setCv(e.target.value)}>
      <option value="">Tous mes CV</option>{mine.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label></div>}
    <p className="mute">Texte de l'offre</p>
    <textarea value={offer} onChange={e => setOffer(e.target.value)} />
    <div className="row">{Object.entries(TASKS).map(([k, l]) => <button key={k} className="btn" disabled={busy} onClick={() => run(k)}>{l}</button>)}</div>
    <div className="card out">{out}</div>
    <button className="btn ghost" onClick={() => navigator.clipboard?.writeText(out)}>Copier</button>
  </>);
}

function CvSlot({ slot, label, cv, busy, onUpload, onSave, onLabel }) {
  const [text, setText] = useState(cv?.text || "");
  const [name, setName] = useState(label);
  const file = useRef();
  useEffect(() => { setText(cv?.text || ""); }, [cv?.text]);
  useEffect(() => { setName(label); }, [label]);
  return (<div className="card">
    <div className="row" style={{ alignItems: "center", margin: 0 }}>
      <Dot ok={!!cv?.text} />
      <input value={name} onChange={e => setName(e.target.value)} onBlur={() => name.trim() && name !== label && onLabel(slot, name)} maxLength={40} aria-label="Nom de ce CV" style={{ fontWeight: 600 }} />
      <span className="mute">{cv?.text ? `enregistré${cv.file ? " (" + cv.file + ")" : ""}` : "pas encore importé"}</span>
    </div>
    <div className="row"><input type="file" ref={file} accept=".pdf,.txt" />
      <button className="btn" disabled={busy} onClick={() => file.current.files[0] && onUpload(slot, file.current.files[0])}>Importer</button></div>
    <details><summary className="mute">Voir, corriger ou supprimer le texte lu</summary>
      <textarea value={text} onChange={e => setText(e.target.value)} style={{ minHeight: 160 }} />
      <div className="row"><button className="btn ghost" disabled={busy} onClick={() => onSave(slot, text)}>Enregistrer ce texte</button>
        {cv?.text && <button className="btn ghost" disabled={busy} onClick={() => onSave(slot, "")}>Supprimer ce CV</button>}</div></details>
  </div>);
}

function Profile({ me, reloadMe, goSettings }) {
  const [p, setP] = useState({ cvs: {}, slots: {}, analysis: null });
  const { msg, busy, act } = useAction();
  useEffect(() => { api("/api/profile").then(setP).catch(() => {}); }, []);
  const done = r => { setP(r); reloadMe(); return r.error ? `CV enregistré, mais analyse impossible pour l'instant : ${r.error}` : "CV enregistré et analysé. Tes offres sont en cours de notation : reviens sur l'onglet Offres dans une minute."; };
  const upload = (slot, f) => act("Lecture et analyse du CV…", async () => {
    const fd = new FormData(); fd.append("file", f);
    return done(await api(`/api/profile/cv?slot=${slot}`, { method: "POST", body: fd }));
  });
  const saveText = (slot, text) => act("Analyse en cours…", async () => done(await put("/api/profile", { slot, text })));
  const saveLabel = (slot, label) => act("Enregistrement…", async () => { setP(await put("/api/profile/label", { slot, label })); reloadMe(); });
  const a = p.analysis;
  return (<>
    {msg && <p className="note">{msg}</p>}
    <h3>Mes CV</h3>
    <p className="mute">Un seul CV suffit. Si tu vises plusieurs domaines, importe une version par domaine et donne-lui un nom : pour chaque offre, l'IA t'indique laquelle envoyer.</p>
    <Quota ai={me.ai} kind="cv" what="analyses de CV" goSettings={goSettings} />
    {Object.entries(p.slots || {}).map(([k, l]) => <CvSlot key={k} slot={k} label={l} cv={p.cvs?.[k]} busy={busy} onUpload={upload} onSave={saveText} onLabel={saveLabel} />)}
    {a && <div className="card">
      <strong>Analyse de ton profil</strong><p>{a.resume}</p>
      <div className="cols"><div><List title="Points forts" items={a.points_forts} /><List title="Postes à viser" items={a.postes_cibles} /></div>
        <div><List title="Points faibles" items={a.points_faibles} /><List title="Améliorations du CV" items={a.conseils_cv} /></div></div>
    </div>}
  </>);
}

const TABS = ["feed", "track", "ai", "profile", "settings", "admin", "privacy"];
const hashLink = () => { const m = window.location.hash.match(/^#(verify|reset)=([\w.]+)$/); return m ? { kind: m[1], token: m[2] } : null; };
const clearHash = () => { try { window.history.replaceState(null, "", window.location.pathname); } catch { window.location.hash = ""; } };
const hashTab = () => { const h = window.location.hash.slice(1); return TABS.includes(h) ? h : "feed"; };

export default function App() {
  const [me, setMeRaw] = useState(undefined);   // undefined : chargement, null : déconnecté
  const [info, setInfo] = useState(null);
  const [tabAsked, setTabRaw] = useState(hashTab);
  const [ctx, setCtx] = useState(null);          // offre ouverte dans l'assistant
  const [feedKey, setFeedKey] = useState(0);     // augmente pour recharger la liste des offres
  const [link, setLink] = useState(hashLink);   // lien reçu par e-mail, s'il y en a un dans l'adresse
  const [flash, setFlash] = useState("");
  useEffect(() => {
    if (link?.kind !== "verify") return;
    post("/api/verify", { token: link.token })
      .then(() => { setFlash("Adresse confirmée. Tes offres vont être notées par l'IA."); if (getToken()) reloadMe(); })
      .catch(e => setFlash(e.message));
    clearHash(); setLink(null);
  }, []);
  const [askCookies, setAskCookies] = useState(false);
  useEffect(() => { if (info?.ga) { audience.resume(info.ga); setAskCookies(!audience.choice()); } }, [info]);
  const consent = <Consent info={info} ask={askCookies} onDone={() => setAskCookies(false)} onMore={() => { if (me) setTab("privacy"); else document.querySelector("#legal footer a:nth-child(2)")?.click(); }} />;
  const [toastMsg, setToastMsg] = useState(null);
  const toastTimer = useRef(0);
  const showToast = useCallback((text, undo) => { clearTimeout(toastTimer.current); setToastMsg({ text, undo }); toastTimer.current = setTimeout(() => setToastMsg(null), 6000); }, []);
  const tabRef = useRef(tabAsked);
  const feedScroll = useRef(0);                  // position de lecture dans la liste des offres
  const setTab = t => { if (t !== tabRef.current) window.location.hash = t; };
  useEffect(() => {
    try { window.history.scrollRestoration = "manual"; } catch { /* navigateur ancien */ }
    const onHash = () => { tabRef.current = hashTab(); setTabRaw(tabRef.current); };
    const onScroll = () => { if (tabRef.current === "feed") feedScroll.current = window.scrollY; };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("hashchange", onHash); window.removeEventListener("scroll", onScroll); };
  }, []);
  // En revenant sur les offres, on retrouve l'endroit exact où l'on s'était arrêté.
  useEffect(() => {
    const y = tabAsked === "feed" ? feedScroll.current : 0;
    const t = setTimeout(() => window.scrollTo(0, y), 0);
    return () => clearTimeout(t);
  }, [tabAsked]);
  useEffect(() => { audience.page(me ? tabAsked : "accueil"); }, [tabAsked, !!me, askCookies]);
  const [apps, setApps] = useState([]);
  const [offer, setOffer] = useState("");
  const [cv, setCv] = useState("");
  const [status, setStatus] = useState(null);
  const setMe = m => setMeRaw(m);
  const reloadMe = useCallback(() => api("/api/me").then(setMeRaw).catch(() => {}), []);
  const reload = () => api("/api/applications").then(setApps).catch(() => {});
  const refreshStatus = useCallback(() => api("/api/status").then(setStatus).catch(() => {}), []);
  const start = m => { setMeRaw(m); refreshStatus(); reload(); };
  setOnLogout(() => { setToken(null); setMeRaw(null); });
  useEffect(() => {
    api("/api/public").then(setInfo).catch(() => {});
    if (!getToken()) return setMeRaw(null);
    api("/api/me").then(start).catch(() => setMeRaw(null));
  }, []);
  useEffect(() => { if (info?.name) document.title = info.name; }, [info]);
  if (me === undefined) return <div className="loading"><div><div className="brand" style={{ justifyContent: "center", fontSize: "1.4rem" }}><Mark />{info?.name || "Veille Stages"}</div><p className="mute">Chargement… (jusqu'à une minute si le serveur dormait)</p></div></div>;
  if (link?.kind === "reset") return <NewPassword info={info} token={link.token} onOk={m => { clearHash(); setLink(null); start(m); }} onCancel={() => { clearHash(); setLink(null); }} />;
  if (!me) return <>{flash && <p className="note flash">{flash}</p>}<Auth info={info} onOk={start} onCookies={() => setAskCookies(true)} />{consent}</>;
  const track = async a => { const r = await post("/api/applications", a); reload(); return r.id; };
  const untrack = async id => { if (id) await api(`/api/applications/${id}`, { method: "DELETE" }); reload(); };
  const toAI = (t, k = "", o = null) => { setOffer(t); setCv(k); setCtx(o); setTab("ai"); };
  const setCtxState = async state => {
    if (!ctx) return;
    if (state === "applied") await track({ company: ctx.company, job: ctx.title, url: ctx.url, status: 1 });
    await api(`/api/offers/${ctx.id}`, { method: "PATCH", body: JSON.stringify({ state }) });
    setCtx({ ...ctx, state }); setFeedKey(k => k + 1);
  };
  const goSettings = e => { e?.preventDefault(); setTab("settings"); };
  const tabs = [["feed", "Offres"], ["track", `Suivi (${apps.length})`], ["ai", "Assistant"], ["profile", "Profil"], ["settings", "Réglages"]];
  if (me.is_admin) tabs.push(["admin", "Administration"]);
  const tab = tabAsked === "privacy" || tabs.some(([k]) => k === tabAsked) ? tabAsked : "feed";
  const out = () => { setToken(null); setMeRaw(null); };
  return (<div className="app">
    <div className="topbar">
      <div className="brand"><Mark />{info?.name || "Veille Stages"}</div>
      <nav className="tabs" aria-label="Sections">{tabs.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} aria-current={tab === k ? "page" : undefined} onClick={() => setTab(k)}>{l}</button>)}</nav>
      <div className="who"><span className="mute">{me.name || me.email}</span><button className="btn quiet" onClick={out}>Se déconnecter</button></div>
    </div>
    <div className="wrap">
      {flash && <p className="note">{flash}</p>}
      <Unverified me={me} />
      {tab === "feed" && <Start me={me} go={setTab} />}
      <div hidden={tab !== "feed"}><Feed me={me} onTrack={track} onUntrack={untrack} onAnalyse={toAI} status={status} refreshStatus={refreshStatus} reloadKey={feedKey} focusId={ctx?.id} toast={showToast} /></div>
      {tab === "track" && <Tracker apps={apps} reload={reload} />}
      {tab === "ai" && <Assistant me={me} setMe={setMe} offer={offer} setOffer={setOffer} cv={cv} setCv={setCv} goSettings={goSettings} ctx={ctx} onBack={() => setTab("feed")} onState={setCtxState} />}
      {tab === "profile" && <Profile me={me} reloadMe={reloadMe} goSettings={goSettings} />}
      {tab === "settings" && <Settings me={me} setMe={m => setMeRaw(m)} reloadMe={reloadMe} onGone={out} info={info} />}
      {tab === "admin" && me.is_admin && <Admin me={me} />}
      {tab === "privacy" && <Legal info={info} />}
      <footer className="mute">
        <a href="#" onClick={e => { e.preventDefault(); setTab("privacy"); }}>Conditions, confidentialité et mentions légales</a>
        {info?.ga && <a href="#" onClick={e => { e.preventDefault(); setAskCookies(true); }}>Cookies</a>}
        {info?.donate && /^https:\/\//.test(info.donate) && <a href={info.donate} target="_blank" rel="noopener noreferrer">Soutenir le site</a>}
      </footer>
    </div>
    <nav className="bottombar" aria-label="Sections">{[["feed", "Offres"], ["track", "Suivi"], ["ai", "Assistant"], ["profile", "Profil"], ["settings", "Réglages"]].map(([k, l]) =>
      <button key={k} className={tab === k ? "on" : ""} aria-current={tab === k ? "page" : undefined} onClick={() => setTab(k)}><Icon name={k} /><span>{l}</span></button>)}</nav>
    {consent}
    {toastMsg && <div className="toast" role="status"><span>{toastMsg.text}</span>{toastMsg.undo && <button onClick={async () => { const u = toastMsg.undo; setToastMsg(null); await u(); }}>Annuler</button>}</div>}
  </div>);
}
