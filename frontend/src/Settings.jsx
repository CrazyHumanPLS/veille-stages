import { useEffect, useState } from "react";
import { api, post, put, Dot, setToken, useAction } from "./api.jsx";

const randomTopic = () => "veille-" + Array.from(crypto.getRandomValues(new Uint8Array(12)), b => "abcdefghjkmnpqrstuvwxyz23456789"[b % 31]).join("");

function Alerts({ me, setMe }) {
  const a = me.alerts;
  const [discord, setDiscord] = useState("");
  const [ntfy, setNtfy] = useState(a.ntfy || "");
  const { msg, busy, act } = useAction();
  useEffect(() => { setNtfy(a.ntfy || ""); }, [a.ntfy]);
  const save = body => act("Enregistrement…", async () => { await setMe(await put("/api/me/alerts", body)); setDiscord(""); return "Enregistré. Clique « Envoyer un test » pour vérifier."; });
  const any = a.discord || a.ntfy || a.telegram;
  return (<>
    <h3>2. Mes alertes</h3>
    <p className="mute">Dès qu'une offre dépasse ton seuil, tu reçois une notification sur ton téléphone. Chacun branche son propre canal : un seul suffit. Sans canal, tout reste consultable sur le site.</p>
    {msg && <p className="note">{msg}</p>}
    {a.error && <p className="err">Dernier envoi en échec : {a.error}</p>}
    <div className="card">
      <strong><Dot ok={a.discord} /> Discord (conseillé, le plus fiable)</strong>
      <details open={!any}><summary className="mute">Comment faire, en 2 minutes</summary>
        <ol>
          <li>Dans Discord, clique sur le <b>+</b> à gauche, puis <b>Créer le mien</b> et <b>Pour mes amis et moi</b> : c'est ton serveur privé.</li>
          <li>Clique sur la roue dentée à côté du salon <b>#général</b>, puis <b>Intégrations</b>, <b>Webhooks</b>, <b>Nouveau webhook</b>.</li>
          <li>Clique <b>Copier l'URL du webhook</b> et colle-la ci-dessous.</li>
          <li>Installe l'application Discord sur ton téléphone et autorise les notifications.</li>
        </ol></details>
      <div className="row"><input type="password" autoComplete="off" value={discord} onChange={e => setDiscord(e.target.value)} placeholder={a.discord ? "Webhook enregistré (colle une nouvelle adresse pour le remplacer)" : "https://discord.com/api/webhooks/…"} style={{ flex: 1, minWidth: 220 }} />
        <button className="btn" disabled={busy || !discord.trim()} onClick={() => save({ discord })}>Enregistrer</button>
        {a.discord && <button className="btn ghost" disabled={busy} onClick={() => save({ discord: "" })}>Retirer</button>}</div>
    </div>
    <div className="card">
      <strong><Dot ok={!!a.ntfy} /> ntfy (sans compte, parfois capricieux)</strong>
      <details><summary className="mute">Comment faire</summary>
        <ol>
          <li>Installe l'application <b>ntfy</b> sur ton téléphone (Play Store ou App Store).</li>
          <li>Clique ci-dessous sur <b>Créer un sujet secret</b>, puis <b>Enregistrer</b>.</li>
          <li>Dans l'application, touche <b>+</b> et recopie exactement ce sujet.</li>
        </ol></details>
      <div className="row"><input value={ntfy} onChange={e => setNtfy(e.target.value)} placeholder="sujet secret" style={{ flex: 1, minWidth: 200 }} />
        <button className="btn ghost" disabled={busy} onClick={() => setNtfy(randomTopic())}>Créer un sujet secret</button>
        <button className="btn" disabled={busy || ntfy === (a.ntfy || "")} onClick={() => save({ ntfy })}>Enregistrer</button></div>
    </div>
    {a.telegram_available && <div className="card">
      <strong><Dot ok={a.telegram} /> Telegram</strong>
      {a.telegram ? <div className="row"><button className="btn ghost" disabled={busy} onClick={() => save({ telegram: false })}>Délier Telegram</button></div> : <>
        <ol>
          <li>Ouvre le bot {a.telegram_bot ? <a href={`https://t.me/${a.telegram_bot}`} target="_blank" rel="noopener noreferrer">@{a.telegram_bot}</a> : "du site"} dans Telegram.</li>
          <li>Envoie-lui ce message : <code>/start {a.telegram_code}</code></li>
          <li>Reviens ici et clique sur le bouton.</li>
        </ol>
        <button className="btn" disabled={busy} onClick={() => act("Recherche de ton message…", async () => { await setMe(await post("/api/me/telegram/link")); return "Telegram relié. Regarde ton téléphone."; })}>J'ai envoyé le code</button></>}
    </div>}
    <div className="row">
      <button className="btn" disabled={busy || !any} onClick={() => act("Envoi…", async () => { await post("/api/me/alerts/test"); return "Message de test envoyé. Regarde ton téléphone."; })}>Envoyer un test</button>
      <label className="check"><input type="checkbox" checked={a.on} onChange={e => save({ on: e.target.checked })} /><span>Alertes activées</span></label>
    </div>
  </>);
}

function Premium({ me, info }) {
  const ai = me.ai, pr = info?.premium, pl = info?.premium_limits;
  if (!ai.premium && !/^https:\/\//.test(pr?.url || "")) return null;   // rien à vendre : on n'affiche rien
  const until = ai.premium && new Date(ai.premium_until * 1000).toLocaleDateString("fr-FR");
  return (<div className={`card premium${ai.premium ? " active" : ""}`}>
    <strong>{ai.premium ? `Tu es en Premium jusqu'au ${until}` : `Premium${pr.price ? `, ${pr.price}` : ""}`}</strong>
    {pl && <ul>
      <li>{pl.score} offres notées par l'IA chaque jour, au lieu de {info.limits.score}.</li>
      <li>{pl.assist} lettres, analyses et messages par jour, au lieu de {info.limits.assist}.</li>
      <li>Aucune clé à créer : tout fonctionne dès l'activation.</li>
    </ul>}
    {!ai.premium && <><a className="btn" href={pr.url} target="_blank" rel="noopener noreferrer">Passer en Premium</a>
      <p className="mute">Lors du paiement, indique l'adresse {me.email}. Ton compte est activé à la main, en général dans la journée.</p></>}
  </div>);
}

function AiKey({ me, setMe }) {
  const ai = me.ai;
  const [key, setKey] = useState("");
  const { msg, busy, act } = useAction();
  const names = { score: "Offres notées d'après ton CV", assist: "Lettres, analyses et messages", cv: "Analyses de CV" };
  return (<>
    <h3>3. Intelligence artificielle</h3>
    {msg && <p className="note">{msg}</p>}
    {ai.error && <p className="err">Dernière erreur de l'IA : {ai.error}</p>}
    <div className="card">
      <strong>Ta consommation aujourd'hui</strong>
      <table><tbody>{Object.entries(ai.kinds).map(([k, v]) => <tr key={k}><td>{names[k]}</td><td>{v.used}{v.limit == null ? " (sans limite)" : ` sur ${v.limit}`}</td></tr>)}</tbody></table>
      <p className="mute">{ai.own_key ? "Tu utilises ta propre clé : pas de limite côté site, seulement celle de Google (très large pour un usage personnel)."
        : ai.premium ? "Tu es en Premium : tes limites sont relevées, sans clé à créer."
        : ai.shared_available ? "Tu utilises la clé commune du site, partagée entre tous les inscrits : d'où ces limites, remises à zéro chaque nuit à minuit. Au-delà, les offres gardent un score par mots-clés."
          : "Ce site n'a pas de clé commune : ajoute la tienne pour activer l'IA."}</p>
    </div>
    <div className="card">
      <strong><Dot ok={ai.own_key} /> Ma propre clé Gemini (gratuite, sans limite côté site)</strong>
      <details open={!ai.own_key && !ai.shared_available}><summary className="mute">Comment l'obtenir, en 2 minutes</summary>
        <ol>
          <li>Ouvre <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">aistudio.google.com/apikey</a> et connecte-toi avec un compte Google.</li>
          <li>Clique <b>Créer une clé API</b> (aucune carte bancaire n'est demandée).</li>
          <li>Copie la clé et colle-la ci-dessous.</li>
        </ol>
        <p className="mute">Elle est chiffrée dans la base, n'est jamais réaffichée et ne sert que pour tes propres demandes. Tu peux la retirer ici ou la supprimer chez Google à tout moment.</p></details>
      <div className="row"><input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} placeholder={ai.own_key ? "Clé enregistrée (colle une nouvelle clé pour la remplacer)" : "Colle ta clé ici"} style={{ flex: 1, minWidth: 220 }} />
        <button className="btn" disabled={busy || !key.trim()} onClick={() => act("Vérification de la clé auprès de Google…", async () => { await setMe(await put("/api/me/gemini", { key })); setKey(""); return "Clé vérifiée et enregistrée. Tu n'as plus de limite."; })}>Enregistrer</button>
        {ai.own_key && <button className="btn ghost" disabled={busy} onClick={() => act("Suppression…", async () => { await setMe(await put("/api/me/gemini", { key: "" })); return "Clé retirée."; })}>Retirer ma clé</button>}</div>
    </div>
  </>);
}

function Search({ reloadMe, info }) {
  const [crit, setCrit] = useState(null);
  const { msg, busy, act } = useAction();
  useEffect(() => { api("/api/criteria").then(setCrit).catch(() => {}); }, []);
  if (!crit) return null;
  const lines = k => ({ value: (crit[k] || []).join("\n"), onChange: e => setCrit({ ...crit, [k]: e.target.value.split("\n") }) });
  const num = k => ({ type: "number", min: 0, max: 100, value: crit[k], onChange: e => setCrit({ ...crit, [k]: +e.target.value }) });
  const save = extra => act("Enregistrement…", async () => { setCrit(await put("/api/criteria", { ...crit, ...extra })); reloadMe(); return "Enregistré. Tes offres sont retriées avec ces réglages (une minute environ)."; });
  const toggle = (k, v) => setCrit({ ...crit, [k]: crit[k].includes(v) ? crit[k].filter(x => x !== v) : [...crit[k], v] });
  const doms = Object.entries(info?.domains || {}), regs = Object.entries(info?.regions || {});
  return (<>
    <h3>1. Ma recherche</h3>
    {msg && <p className="note">{msg}</p>}
    <div className="card">
      <fieldset className="choices">
        <legend>Mes domaines</legend>
        {doms.map(([k, l]) => <label key={k} className={crit.domains.includes(k) ? "on" : ""}><input type="checkbox" checked={crit.domains.includes(k)} onChange={() => toggle("domains", k)} />{l}</label>)}
      </fieldset>
      {!crit.domains.length && <p className="err">Coche au moins un domaine.</p>}
      <fieldset className="choices">
        <legend>Mes régions</legend>
        <label className={!crit.regions.length ? "on" : ""}><input type="checkbox" checked={!crit.regions.length} onChange={() => setCrit({ ...crit, regions: [] })} />Toute la France</label>
        {regs.map(([k, l]) => <label key={k} className={crit.regions.includes(k) ? "on" : ""}><input type="checkbox" checked={crit.regions.includes(k)} onChange={() => toggle("regions", k)} />{l}</label>)}
      </fieldset>
      <p className="mute">Les offres en télétravail ou sans lieu précisé te sont proposées quelles que soient tes régions.</p>
      <label className="block">Ce que tu veux comme stage (durée, date, spécialité, ville)
        <textarea value={crit.goal} maxLength={300} onChange={e => setCrit({ ...crit, goal: e.target.value })} style={{ minHeight: 60 }} /></label>
      <p className="mute">Ton CV dit ce que tu sais faire, cette phrase dit ce que tu veux : l'IA utilise les deux pour noter les offres et écrire tes lettres. Elle est remplie d'après ton CV au premier import, corrige-la librement. Exemple : « Stage de fin d'études de 6 mois à partir de mars 2027, en logiciel embarqué ou FPGA, à Toulouse ou en Île-de-France ».</p>
      <div className="row">
        <label>M'alerter si le score de l'IA atteint <input {...num("notify_ai")} /></label>
        <label>Sans IA, si le score par mots-clés atteint <input {...num("notify_kw")} /></label>
        <label>Ne pas me proposer sous <input {...num("min_kw")} /></label>
        <label>Faire noter par l'IA à partir de <input {...num("ai_min_kw")} /></label>
      </div>
      <p className="mute">Ces deux derniers seuils portent sur le score par mots-clés. Sous le seuil de l'IA, une offre reste affichée avec son score par mots-clés mais n'est pas envoyée à l'IA : ça économise ton quota.</p>
      <details><summary className="mute">Mots-clés (réglage avancé){crit.custom_lists?.length ? " : listes personnalisées" : " : listes de tes domaines"}</summary>
        <div className="cols">
          <div><h4>Mots-clés forts (un par ligne)</h4><textarea {...lines("strong")} /></div>
          <div><h4>Technologies et outils (un par ligne)</h4><textarea {...lines("tech")} /></div>
          <div><h4>Mots tirés de ton CV (remplis par l'analyse)</h4><textarea {...lines("profile_keywords")} /></div>
          <div><h4>Mots à pénaliser dans le titre</h4><textarea {...lines("negative")} /></div>
        </div>
        {crit.custom_lists?.length > 0 && <button className="btn ghost" disabled={busy} onClick={() => save({ reset_lists: true, strong: undefined, tech: undefined, negative: undefined })}>Revenir aux listes de mes domaines</button>}
      </details>
      <button className="btn" disabled={busy || !crit.domains.length} onClick={() => save()}>Enregistrer ma recherche</button>
    </div>
  </>);
}

function Account({ me, setMe, onGone }) {
  const [name, setName] = useState(me.name || "");
  const [pw, setPw] = useState({ old: "", new: "" });
  const [del, setDel] = useState("");
  const { msg, busy, act } = useAction();
  const download = () => act("Préparation…", async () => {
    const data = await api("/api/me/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "mes-donnees.json"; a.click(); URL.revokeObjectURL(url);
    return "Fichier téléchargé.";
  });
  return (<>
    <h3>4. Mon compte</h3>
    {msg && <p className="note">{msg}</p>}
    <div className="card">
      <p className="mute">Connecté avec {me.email}</p>
      <div className="row"><label>Prénom <input value={name} maxLength={80} onChange={e => setName(e.target.value)} /></label>
        <button className="btn ghost" disabled={busy || name === (me.name || "")} onClick={() => act("Enregistrement…", async () => { await setMe(await put("/api/me", { name })); })}>Enregistrer</button></div>
      <h4>Changer de mot de passe</h4>
      <div className="row">
        <input type="password" placeholder="Mot de passe actuel" autoComplete="current-password" value={pw.old} onChange={e => setPw({ ...pw, old: e.target.value })} />
        <input type="password" placeholder="Nouveau (8 caractères min.)" autoComplete="new-password" value={pw.new} onChange={e => setPw({ ...pw, new: e.target.value })} />
        <button className="btn ghost" disabled={busy || !pw.old || pw.new.length < 8} onClick={() => act("Changement…", async () => { const r = await post("/api/me/password", pw); setToken(r.token); setPw({ old: "", new: "" }); return "Mot de passe changé. Tes autres appareils sont déconnectés."; })}>Changer</button>
      </div>
      <h4>Mes données</h4>
      <div className="row"><button className="btn ghost" disabled={busy} onClick={download}>Télécharger toutes mes données</button></div>
      <details><summary className="err">Supprimer mon compte</summary>
        <p className="mute">Ton compte, tes CV, tes candidatures et tes réglages sont effacés tout de suite et pour de bon.</p>
        <div className="row"><input type="password" placeholder="Ton mot de passe pour confirmer" value={del} onChange={e => setDel(e.target.value)} />
          <button className="btn danger" disabled={busy || !del} onClick={() => act("Suppression…", async () => { await post("/api/me/delete", { password: del }); onGone(); return "Compte supprimé."; })}>Supprimer définitivement</button></div>
      </details>
    </div>
  </>);
}

export default function Settings({ me, setMe, reloadMe, onGone, info }) {
  return (<>
    <Search reloadMe={reloadMe} info={info} />
    <Alerts me={me} setMe={setMe} />
    <AiKey me={me} setMe={setMe} />
    <Premium me={me} info={info} />
    <Account me={me} setMe={setMe} onGone={onGone} />
  </>);
}
