# Veille Stages (version publique) — contexte pour reprendre le projet

Créé le 06/10/2026 à partir de l'application personnelle `stage-app` (même auteur, voir son propre CLAUDE.md).
À tenir à jour à chaque évolution importante.

## L'utilisateur et son besoin

- Aghiles, étudiant en M2 (UVSQ, Paris-Saclay). Il veut ouvrir sa veille de stages à ses amis, puis à tous.
- N'est pas développeur de métier : étapes numérotées, concrètes, en français, noms exacts des boutons.
  Il utilise **GitHub Desktop** sous Windows. Tout doit rester **gratuit**.
- **Ne jamais modifier le dossier `stage-app`** (son application personnelle) : ce projet vit à côté.

## Où tout se trouve

| Élément | Emplacement |
|---|---|
| Code sur le PC | `C:\Users\User\Downloads\stage-m2-app\veille-stages` |
| Dépôt GitHub | privé, poussé par l'utilisateur avec GitHub Desktop |
| Site | https://veille-stages.onrender.com (en ligne depuis le 06/10/2026), base Supabase |

Variables d'environnement (valeurs dans Render uniquement) : `DATABASE_URL`, `SECRET_KEY` (créée par Render,
ne jamais la changer), `ADMIN_EMAIL`, `CRON_KEY`, `APP_URL`, `APP_NAME`, `GEMINI_API_KEY` (clé commune),
`GEMINI_MODEL`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `SIGNUP_MODE`, `INVITE_CODE`, `CONTACT_EMAIL`, `DONATE_URL`,
`TELEGRAM_TOKEN`, `TELEGRAM_BOT`, `COLLECT_EVERY_SEC`, `LEGAL_NAME`, `PREMIUM_URL`, `PREMIUM_PRICE`, `GA_ID`, `BREVO_API_KEY`, `MAIL_FROM`,
`GOOGLE_VERIFY` (code Search Console), `SEO_PER_WEEK` (2 par défaut).

## Choix de conception (décidés le 06/10/2026, l'utilisateur a délégué)

- **Offres communes, tout le reste par utilisateur.** Table `offers` partagée ; `user_offers` porte pour chaque
  personne son score par mots-clés, la note de l'IA, le CV conseillé, l'état (new/saved/hidden/applied),
  l'alerte envoyée ou non. `applications` et `usage` ont un `user_id`.
- **Coût de l'IA nul pour le propriétaire.** Clé commune avec limites par jour et par personne (40 notes,
  5 générations, 6 analyses de CV, plafond global 800 appels) ou clé Gemini personnelle sans limite.
  Réglable dans Administration (kv `limits`). Pas de publicité : rapporte trop peu à cette échelle. Lien de don
  facultatif (`DONATE_URL`).
- **Alertes par personne** : webhook Discord personnel (conseillé), sujet ntfy, ou Telegram si le site a un bot.
- **Comptes** : e-mail + mot de passe (scrypt), jeton signé 30 jours, pas d'envoi d'e-mail. Mot de passe oublié :
  l'administrateur en crée un provisoire. Le premier compte (ou celui de `ADMIN_EMAIL`) est administrateur.
- **Périmètre de la collecte** : stages uniquement, toute la France, six domaines (voir « Élargissement » plus bas).
- Comptes inactifs depuis 21 jours : veille en pause. 300 inscrits maximum par défaut.

## Architecture

- `backend/main.py` : API FastAPI (comptes, réglages, offres, assistant, administration), sert le site compilé.
- `backend/collector.py` : `collect()` (stock commun) puis `process_user()` pour chaque compte actif
  (tri, notation dans la limite du quota, alertes). `resync_one()` après un changement de CV ou de mots-clés.
- `backend/accounts.py` : comptes, réglages, secrets chiffrés. `backend/security.py` : mots de passe, jetons, chiffrement.
- `backend/quota.py` : qui paie l'IA, limites, consommation du jour.
- `backend/scoring.py`, `sources.py`, `ai.py`, `notify.py`, `cvstore.py`, `db.py` : repris de `stage-app`, adaptés
  pour recevoir l'utilisateur ou sa clé en paramètre.
- `backend/board.py` : vitrine publique (offres de la semaine par domaine) et textes de publications.
- `backend/seo.py` : pages HTML écrites par le serveur pour Google (`/stages…`), plan du site, robots.txt.
- `backend/tests/test_pipeline.py` : tests avec réseau simulé (`python -m pytest -q` dans `backend`).
- `frontend/src/` : `App.jsx` (connexion, offres, suivi, assistant, profil), `Board.jsx` (vitrine publique), `Settings.jsx`, `Admin.jsx`, `api.jsx`.

## Règles de travail (reprises de stage-app)

1. Vérifier chaque écriture sur le PC en relisant les fichiers et en comparant leur empreinte.
2. Pas d'accès au dépôt GitHub : l'utilisateur fait Commit puis Push dans GitHub Desktop.
3. Les vraies API ne sont pas testables depuis la session : tests avec réponses simulées, et le dire clairement.
4. `create_all` n'ajoute pas de colonne à une table existante : passer par la boucle `ALTER TABLE` de `db.py`.
5. Les réglages enregistrés (kv `criteria`, `limits`, `site`) priment sur les valeurs par défaut du code.
6. `CRON_KEY` : lettres et chiffres uniquement. `/api/collect` est bloqué par les bloqueurs de publicité.

## Points à surveiller

- Render gratuit : 750 heures par mois pour tout le compte. Deux services réveillés en permanence
  (celui-ci et `stage-m2`) dépassent le quota. Voir le README.
- Les quotas gratuits de Gemini changent souvent : ajuster le plafond global dans Administration d'après
  ce qu'affiche Google AI Studio pour la clé commune.
- Avec une clé gratuite, Google peut utiliser les textes envoyés : c'est écrit dans la page Confidentialité.

## État au 06/10/2026 (soir)

- **En ligne** sur Render (nouveau service) avec une nouvelle base Supabase ; l'ancien service `stage-m2` est suspendu.
  L'utilisateur a confirmé que tout fonctionne avec les vraies API.
- Ajouts du jour : navigation avec le bouton Retour du navigateur (onglets dans l'adresse, `#feed`, `#ai`…),
  rappel de l'offre dans l'Assistant avec « Garder » et « J'ai postulé », seuil `ai_min_kw` (40 par défaut : l'IA ne
  note pas les offres sous ce score par mots-clés), nouveau design (surligneur, polices Bricolage Grotesque et
  Figtree hébergées sur le site, barre d'onglets en bas sur téléphone, message « Annuler »).
- Sécurité : plafonds d'inscription pour tout le site, limitation des connexions sur les échecs seulement, liens
  d'offres limités à http(s), en-têtes de sécurité (CSP), mentions Discord neutralisées, limites sur les retris,
  taille des PDF (4 Mo) et des flux RSS (5 Mo). Relecture faite à la main ; le plugin claude-security n'a pas pu
  tourner dans la session (outil de workflow indisponible) : analyse complète à refaire avant une ouverture large.
- Passage « version professionnelle » (06/10 soir) : appels Gemini fiabilisés (3 essais espacés par modèle, délai
  total plafonné, modèle de secours ; `ai.generate`), formule Premium (colonne `users.plan_until`, limites `p_score`,
  `p_assist`, `p_cv`, activée à la main par l'administrateur avec « +30 j Premium », lien de paiement `PREMIUM_URL` et
  prix `PREMIUM_PRICE`), statistiques d'usage dans Administration, parcours de démarrage en 2 étapes, conditions
  d'utilisation et mentions légales (`LEGAL_NAME`, `CONTACT_EMAIL`), écran d'erreur, site installable sur téléphone
  (`frontend/public/manifest.webmanifest` et icônes, sans service worker pour éviter les versions périmées).
- Mesure d'audience facultative : variable `GA_ID` (Google Analytics). Bandeau « Refuser / Accepter », rien n'est
  chargé avant l'accord (`frontend/src/analytics.js`), lien « Cookies » en bas de page pour changer d'avis. Sans
  `GA_ID` : aucun bandeau, aucun cookie de mesure.
- E-mails (06/10, 19 h) : `backend/mailer.py` envoie par l'API de Brevo (Render gratuit bloque les ports SMTP).
  Variables `BREVO_API_KEY` et `MAIL_FROM`. Confirmation d'adresse à l'inscription (colonne `users.email_verified`,
  les comptes existants sont considérés confirmés ; sans confirmation, pas d'accès à la clé Gemini commune ; le rôle
  administrateur lié à `ADMIN_EMAIL` n'est donné qu'à la confirmation). Mot de passe oublié : lien valable une heure,
  à usage unique (`/api/password/forgot`, `/api/password/reset`). Liens du type `/#verify=…` et `/#reset=…`.
  Sans ces variables, rien ne change. Jamais testé avec un vrai compte Brevo au moment de l'écriture.
- Élargissement (06/10, 20 h) : le stock commun couvre **toute la France** et **six domaines** (`backend/domains.py` :
  réseaux-cyber-cloud, embarqué-électronique, développement, data-IA, industrie-mécanique, gestion). Chaque inscrit
  coche ses domaines et ses régions (Réglages → 1. Ma recherche ; réglages `domains` et `regions`, liste de régions
  vide = toute la France). Sans choix : réseaux + Île-de-France, donc rien ne change pour les comptes existants.
  Le domaine « reseaux » garde les mots-clés de l'onglet Administration ; les autres sont dans `domains.py`.
  Adzuna n'est interrogé que pour les domaines cochés par au moins un compte actif, sur toute la France, avec un
  intervalle qui s'allonge quand il y a plus de requêtes (`ADZUNA_CALLS_PER_DAY`, 96 par défaut).
  Limites connues : toujours des stages uniquement (pas d'alternance) ; une petite ville française absente des
  listes de `domains.py` n'est reconnue que par son numéro de département ; les pages carrières listées dans
  `companies.json` restent surtout des entreprises du numérique.
- Sources (06/10, 23 h) : `companies.json` passe de 43 à 96 sources (52 pages Greenhouse vérifiées une à une avec au
  moins une offre en France, plus le flux RSS de l'AFJV). `collector.py` lit au plus 6 sources à la fois
  (`COLLECT_PARALLEL`) pour ménager la mémoire de Render. Pistes vérifiées mais non faites : The Muse, Jooble et Careerjet (clé à demander) ; Workable et
  Teamtailor sont faits (voir plus bas). Il n'existe pas de source gratuite couvrant « toutes les entreprises de France ».
  L'utilisateur a demandé d'économiser son quota Claude : pas d'agents de recherche en série.
- Pannes Render « health check timed out » (07/10) : la collecte tourne dans le même processus que le site et le
  tri des offres (calcul bloquant) figeait le serveur. Corrigé : `store`, `sync_user`, `load_seen`, `prune` et la
  lecture des réponses Greenhouse passent par `asyncio.to_thread` ; recherche de mots-clés accélérée (`scoring._has`,
  `title_key` en cache). Mesure avec réseau simulé (58 pages de 400 offres) : pire gel du site 0,3 s contre 2,4 s et plus.
  Règle : aucun traitement long directement dans une fonction `async`.
- Annonces anciennes (07/10) : une offre mise en ligne depuis plus de 20 jours (`OFFER_MAX_DAYS`) n'entre plus dans le
  stock et n'est plus proposée (`scoring.too_old`, `collector.keep`, `sync_user`). Sans date connue, elle est gardée.
  Les offres déjà affichées chez un inscrit ne sont pas retirées.
- Réglages d'après le CV (07/10) : à la première analyse de CV d'un compte qui n'a encore rien réglé, l'IA renvoie
  aussi `domaines` et `objectif` (`ai.analyse_cv`) ; `main._analyse` les enregistre comme domaines et phrase de
  recherche. Dès que la personne a choisi elle-même, ses choix ne sont plus modifiés. `FIRST_RUN_AI` passe de 40 à 30
  pour laisser 10 notes aux nouveautés le jour de l'inscription.
- Clé personnelle (07/10) : en l'enregistrant, les offres restées sans note de l'IA (au-dessus de `ai_min_kw`, non
  masquées) repassent en file (`collector.requeue_unscored`) et sont notées, 40 par passage ; le plafond
  `FIRST_RUN_AI` ne s'applique plus à qui a sa propre clé. Ces offres peuvent déclencher une alerte ou un récapitulatif.
- Mémoire (07/10, 15 h) : Render signalait « Ran out of memory (512MB) » depuis l'ajout des 52 pages Greenhouse,
  car `content=true` téléchargeait le texte de toutes les annonces (plusieurs Mo par entreprise). `sources.greenhouse`
  lit maintenant la liste sans texte, puis le détail des seuls stages en France pas encore lus (25 par passage,
  mémoire `_gh_done`). Conséquence : un stage Greenhouse dont le titre ne dit ni « stage » ni « intern » n'est plus vu.
  Règle : ne jamais charger le texte complet de toutes les annonces d'une source.
- Connecteurs Workable et Teamtailor (07/10, refaits le 08/10) : `sources.workable` et `sources.teamtailor`, ajoutés à
  `sources.ATS` (rubriques `workable` et `teamtailor` de `companies.json`, 8 sources : Hugging Face, Withings, Exotec ;
  Skello, Ornikar, Pasqal, Papernest, Indy). Workable suit la règle mémoire : liste sans texte
  (`apply.workable.com/api/v1/widget/accounts/XXX`), puis `?details=true` seulement s'il y a un stage en France pas
  encore lu (`_wk_done`). Teamtailor : flux `XXX.teamtailor.com/jobs.rss` (léger, plafonné à 5 Mo), lieux dans
  `tt:locations`, champ `url` facultatif pour un domaine propre. Format réel lu une fois ; le code n'a tourné qu'avec
  des réponses simulées. **Incident** : la première version (07/10 matin) a été effacée de `sources.py`, des tests et de
  ce fichier par la correction mémoire de 15 h, faite dans une autre conversation à partir d'une copie plus ancienne ;
  `companies.json` gardait les rubriques, donc elles étaient ignorées sans erreur. Règle : toujours relire les fichiers
  du PC juste avant de les modifier, ne jamais repartir d'une copie de la conversation.
- Dates des fausses annonces des tests calculées d'après le jour du test (sinon tout échouait après le 25/10/2026).
- Vitrine publique et publications (08/10) : objectif de l'utilisateur = 300 à 500 € par mois en ligne pour financer
  l'application. Plan retenu : contenu tiré du stock → page publique → inscriptions → Premium. `backend/board.py`
  calcule, au plus toutes les 10 minutes, les offres de la semaine par domaine (score par mots-clés du domaine ≥ 40,
  nouveautés de 48 h d'abord). `GET /api/public/offers?domain=&region=` (sans compte, 8 offres, 60 demandes par minute
  et par adresse) ; page `/#offres` et `/#offres/<domaine>` (`frontend/src/Board.jsx`, lien depuis la page d'accueil).
  `GET /api/admin/posts` + Administration → « Publications du jour » : textes X (280 caractères au plus), LinkedIn et
  script de vidéo, sans IA, une offre par entreprise, bouton Copier. L'utilisateur relit et publie lui-même : Claude ne
  publie rien sur ses comptes sans validation. Écartés : recopier des tweets viraux, dropshipping, Comeup/Malt (pas de
  clients sans historique). À vérifier par l'utilisateur avant de faire payer : statut de micro-entrepreneur et
  conditions d'usage d'Adzuna et de France Travail (affichage public et usage commercial).
- Référencement Google (10/10) : l'utilisateur a demandé à Claude d'agir en agent SEO autonome, en suivant un article
  (mots-clés à intention d'achat, un motif de mots-clés = une série de pages, quelque chose d'unique par page,
  publication lente et régulière, liens internes, puis liens entrants et citations par les IA). Décision : rester sur
  Veille Stages plutôt que lancer un autre produit ; motif retenu « stage [domaine] [ville ou région] ».
  Constat de départ : le site était invisible (application React, adresse en `#`, rien à lire sans JavaScript, pas de
  plan du site, pas de Search Console). Fait : `backend/seo.py` écrit en HTML `/stages` (sommaire),
  `/stages/<domaine>` et `/stages/<domaine>/<région>` à partir du calcul de `board.py` (aucune requête ni IA en plus),
  avec la feuille de style compilée du site. Chaque page : 12 offres, entreprises qui recrutent, villes, compétences
  les plus citées (`tech` ajouté aux offres dans `board._scan`), fil d'Ariane, données structurées, liens vers les
  seules pages fournies. Une page de région ne compte que les offres situées dans la région (pas « France »).
  Garde-fous : moins de 3 offres (`MIN_OFFERS`) = `noindex` et hors plan du site ; ouverture progressive gardée dans
  kv `seo_pages` (les domaines d'abord, puis `SEO_PER_WEEK` pages de région par semaine, une page ouverte le reste).
  `/robots.txt`, `/sitemap.xml`, balise de vérification `GOOGLE_VERIFY` sur l'accueil et les pages. La page d'accueil
  est maintenant servie par `main.home` (ajout de l'adresse officielle), `frontend/index.html` a un vrai titre et un
  texte de secours avec les liens vers les six domaines (les adresses de `seo.SLUGS` ne doivent plus changer).
  Les offres ne sont pas balisées `JobPosting` : Google le réserve aux pages où l'on peut postuler.
  Test `test_emails` : il échouait une fois sur seize (jeton trafiqué identique à l'original), corrigé.
  Vérifié : 16 tests, et rendu regardé sur ordinateur et téléphone avec des offres d'exemple ; jamais vu avec le
  stock réel avant le push. À faire par l'utilisateur : Search Console (README « Être trouvé sur Google »).
  Suite prévue : lire Search Console après 2 à 3 semaines, pages par métier précis (« stage data analyst »,
  « stage cybersécurité ») si le stock suit, alternance (budget côté entreprises), liens entrants gratuits (écoles,
  associations étudiantes, annuaires d'outils), nom de domaine propre dès qu'il y a des revenus (une adresse
  `onrender.com` ne garde pas son acquis si on change d'hébergeur).
- 16 tests automatiques réussis. Les derniers lots sont à pousser par l'utilisateur (GitHub Desktop).
- Accès GitHub : seul `ChampionsLeague_DB` est autorisé pour Claude ; l'utilisateur doit ajouter `veille-stages`
  dans les dépôts autorisés pour que la session puisse pousser elle-même.

## Pistes non faites

L'utilisateur vise à terme une vraie application (web puis mobile) rapportant 200 à 300 € par mois. Ordre conseillé :
mesurer l'usage (statistiques dans Administration), puis alternance et toute la France, alertes par e-mail,
vérification d'adresse et mot de passe oublié (demande un service d'envoi d'e-mails), paiement automatique
(Stripe) à la place de l'activation manuelle du Premium, puis application sur les stores.
