import { useCallback, useEffect, useRef, useState } from "react";
import { api, post, put, ago, Dot, List, getToken, setToken, setOnLogout, useAction } from "./api.jsx";
import Settings from "./Settings.jsx";
import Admin from "./Admin.jsx";

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
    </ul>
    <p className="mute">Site gratuit, tenu par un étudiant, sans publicité ni traceur.{info?.contact && <> Contact : {info.contact}</>}</p>
  </div>);
}

function Auth({ info, onOk }) {
  const closed = info?.signup === "closed";
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ email: "", password: "", name: "", invite: "", consent: false });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);
  const set = k => e => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const go = async e => {
    e.preventDefault(); setErr(""); setBusy(true);
    try { const r = await post(mode === "login" ? "/api/login" : "/api/signup", f); setToken(r.token); onOk(r.me); }
    catch (x) { setErr(x.message); }
    setBusy(false);
  };
  const lim = info?.limits;
  return (<div className="wrap login">
    <h1>{info?.name || "Veille Stages"}</h1>
    <p className="lead">Les offres de stage arrivent toutes seules, notées d'après ton CV, avec une alerte sur ton téléphone dès qu'une bonne offre sort.</p>
    <div className="tabs2">
      <button className={mode === "login" ? "on" : ""} onClick={() => { setMode("login"); setErr(""); }}>Se connecter</button>
      <button className={mode === "signup" ? "on" : ""} onClick={() => { setMode("signup"); setErr(""); }}>Créer un compte</button>
    </div>
    {mode === "signup" && closed ? <p className="note">Les inscriptions sont fermées pour le moment.</p> :
      <form className="card form" onSubmit={go}>
        {mode === "signup" && <label>Prénom<input value={f.name} onChange={set("name")} maxLength={80} autoComplete="given-name" /></label>}
        <label>Adresse e-mail<input type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label>Mot de passe{mode === "signup" && " (8 caractères minimum)"}<input type="password" required minLength={mode === "signup" ? 8 : 1} value={f.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {mode === "signup" && info?.signup === "invite" && <label>Code d'invitation<input required value={f.invite} onChange={set("invite")} /></label>}
        {mode === "signup" && <label className="check"><input type="checkbox" checked={f.consent} onChange={set("consent")} />
          <span>J'accepte que mon CV soit enregistré et analysé pour me proposer des offres. <a href="#" onClick={e => { e.preventDefault(); setShowPrivacy(!showPrivacy); }}>Voir le détail</a></span></label>}
        <button className="btn" disabled={busy}>{busy ? "Un instant…" : mode === "login" ? "Se connecter" : "Créer mon compte"}</button>
        {err && <p className="err">{err}</p>}
        {mode === "login" && <p className="mute">Mot de passe oublié ? Demande à la personne qui t'a donné l'adresse du site : elle peut t'en créer un nouveau.</p>}
      </form>}
    {showPrivacy && <Privacy info={info} />}
    {mode === "signup" && !closed && <div className="card">
      <strong>Gratuit, et ça le reste</strong>
      <ul>
        <li>Offres collectées en continu sur les sites carrières et les agrégateurs.</li>
        {lim && info.shared_ai && <li>IA incluse pour essayer : {lim.score} offres notées et {lim.assist} lettres ou analyses par jour.</li>}
        <li>Sans limite si tu ajoutes ta propre clé Gemini (gratuite, 2 minutes).</li>
        <li>Alertes sur ton téléphone par Discord ou ntfy.</li>
      </ul>
    </div>}
  </div>);
}

function Feed({ me, onTrack, onAnalyse, status, refreshStatus }) {
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
  useEffect(() => { load(); const t = setInterval(() => { load(); refreshStatus(); }, 60000); return () => clearInterval(t); }, [load]);
  const setState = async (o, state) => { await api(`/api/offers/${o.id}`, { method: "PATCH", body: JSON.stringify({ state }) }); load(); };
  const refresh = async () => {
    setBusy(true); setNote(""); setErr("");
    try {
      const r = await post("/api/refresh");
      setNote(r.setup ? "Importe ton CV dans l'onglet Profil : tes offres seront notées et tes alertes activées."
        : r.waiting ? `Notation en cours : ${r.scored} offre(s) notée(s), la suite arrive dans quelques minutes.`
        : `À jour : ${r.new} nouvelle(s) offre(s) pour toi, ${r.scored} notée(s) par l'IA, ${r.alerts} alerte(s) envoyée(s).`);
    } catch (e) { setErr(e.message); }
    setBusy(false); load(); refreshStatus();
  };
  const analyse = async o => { const full = await api(`/api/offers/${o.id}`); onAnalyse(`${full.title}\n${full.company} · ${full.place}\n\n${full.description}`, full.cv || ""); };
  const run = status?.last_run;
  return (<>
    <div className="stats">
      <div><b>{status?.last_24h ?? "…"}</b><span>nouvelles en 24 h</span></div>
      <div><b>{status?.total ?? "…"}</b><span>offres pour toi</span></div>
      <div><b>{run ? ago(run.at) : "jamais"}</b><span>dernière collecte</span></div>
      <button className="btn ghost" onClick={refresh} disabled={busy}>{busy ? "Mise à jour…" : "Actualiser"}</button>
    </div>
    <div className="row">
      <select value={f.state} onChange={e => setF({ ...f, state: e.target.value })}>
        <option value="new">Nouvelles</option><option value="saved">Gardées</option><option value="applied">Postulées</option>
        <option value="hidden">Masquées</option><option value="all">Toutes</option></select>
      <select value={f.min} onChange={e => setF({ ...f, min: +e.target.value })}>
        <option value={0}>Tous les scores</option><option value={55}>Score 55 et plus</option><option value={75}>Score 75 et plus</option></select>
      <select value={f.hours} onChange={e => setF({ ...f, hours: +e.target.value })}>
        <option value={0}>Toutes dates</option><option value={2}>2 dernières heures</option><option value={24}>24 h</option><option value={72}>3 jours</option></select>
      <select value={sort} onChange={e => setSort(e.target.value)}>
        <option value="seen">Tri : détectées récemment</option><option value="pub">Tri : mises en ligne récemment</option><option value="score">Tri : meilleur score</option></select>
      <input value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Filtrer (entreprise, techno…)" style={{ flex: 1, minWidth: 160 }} />
    </div>
    {note && <p className="note">{note}</p>}
    {err && <p className="err">{err}</p>}
    {list && !list.length && <p className="mute">Aucune offre ici pour l'instant. La collecte tourne en continu ; tes mots-clés se règlent dans l'onglet Réglages.</p>}
    {list && [...list].sort((a, b) => sort === "score" ? best(b) - best(a)
      : sort === "pub" ? (b.published || "0").localeCompare(a.published || "0") : b.first_seen - a.first_seen).map(o => (
      <div className="card offer" key={o.id}>
        <div className={`score ${tone(best(o))}`} title={o.ai_score == null ? "Score par mots-clés" : "Score de l'IA d'après ton CV"}>{best(o)}{o.ai_score == null && <small>mots-clés</small>}</div>
        <div className="body">
          <strong>{o.title}</strong>
          <div className="mute">{o.company || "Entreprise non précisée"} · {o.place || "lieu non précisé"} · {o.source}</div>
          <div className="mute">{pubLabel(o.published)} · détectée {ago(o.first_seen)}</div>
          {me.cv > 1 && o.cv && <span className="tag">CV à envoyer : {me.cv_labels?.[o.cv] || o.cv}</span>}
          {o.dup_note && <p className="warn">{o.dup_note}</p>}
          {o.ai_reason ? <p className="why">{o.ai_reason}</p> : o.excerpt && <p className="mute">{o.excerpt.slice(0, 220)}…</p>}
          <div className="row">
            <a className="btn" href={o.url} target="_blank" rel="noopener noreferrer">Voir l'offre</a>
            <button className="btn ghost" onClick={() => analyse(o)}>Lettre et analyse</button>
            <button className="btn ghost" onClick={async () => { await onTrack({ company: o.company, job: o.title, url: o.url, status: 1 }); setState(o, "applied"); }}>J'ai postulé</button>
            {o.state !== "saved" && <button className="btn ghost" onClick={() => setState(o, "saved")}>Garder</button>}
            {o.state !== "hidden" && <button className="btn ghost" onClick={() => setState(o, "hidden")}>Masquer</button>}
          </div>
        </div>
      </div>))}
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
    <div className="card"><strong>{sent}</strong> candidature(s) envoyée(s) · <strong>{apps.filter(late).length}</strong> à relancer</div>
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

function Assistant({ me, setMe, offer, setOffer, cv, setCv, goSettings }) {
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

export default function App() {
  const [me, setMeRaw] = useState(undefined);   // undefined : chargement, null : déconnecté
  const [info, setInfo] = useState(null);
  const [tab, setTab] = useState("feed");
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
  if (me === undefined) return <div className="wrap"><p className="mute">Chargement… (jusqu'à une minute si le serveur dormait)</p></div>;
  if (!me) return <Auth info={info} onOk={start} />;
  const track = async a => { await post("/api/applications", a); reload(); };
  const toAI = (t, k = "") => { setOffer(t); setCv(k); setTab("ai"); };
  const goSettings = e => { e?.preventDefault(); setTab("settings"); };
  const hasAlerts = me.alerts.discord || me.alerts.ntfy || me.alerts.telegram;
  const todo = [!me.cv && ["importer ton CV", "profile"], !hasAlerts && ["brancher tes alertes", "settings"]].filter(Boolean);
  const tabs = [["feed", "Offres"], ["track", `Suivi (${apps.length})`], ["ai", "Assistant"], ["profile", "Profil"], ["settings", "Réglages"]];
  if (me.is_admin) tabs.push(["admin", "Administration"]);
  return (<div className="wrap">
    <header>
      <h1>{info?.name || "Veille Stages"}</h1>
      <div className="who"><span className="mute">{me.name || me.email}</span>
        <button className="btn ghost" onClick={() => { setToken(null); setMeRaw(null); }}>Se déconnecter</button></div>
    </header>
    {todo.length > 0 && <p className="note">Pour finir l'installation, il reste à {todo.map(([l, t], i) => <span key={t}>{i > 0 && " et à "}<a href="#" onClick={e => { e.preventDefault(); setTab(t); }}>{l}</a></span>)}.</p>}
    <nav>{tabs.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</nav>
    {tab === "feed" && <Feed me={me} onTrack={track} onAnalyse={toAI} status={status} refreshStatus={refreshStatus} />}
    {tab === "track" && <Tracker apps={apps} reload={reload} />}
    {tab === "ai" && <Assistant me={me} setMe={setMe} offer={offer} setOffer={setOffer} cv={cv} setCv={setCv} goSettings={goSettings} />}
    {tab === "profile" && <Profile me={me} reloadMe={reloadMe} goSettings={goSettings} />}
    {tab === "settings" && <Settings me={me} setMe={m => setMeRaw(m)} reloadMe={reloadMe} onGone={() => { setToken(null); setMeRaw(null); }} />}
    {tab === "admin" && me.is_admin && <Admin me={me} />}
    {tab === "privacy" && <Privacy info={info} />}
    <footer className="mute">
      <a href="#" onClick={e => { e.preventDefault(); setTab("privacy"); }}>Confidentialité et données</a>
      {info?.donate && /^https:\/\//.test(info.donate) && <> · <a href={info.donate} target="_blank" rel="noopener noreferrer">Soutenir le site</a></>}
    </footer>
  </div>);
}
