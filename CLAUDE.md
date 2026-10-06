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
| Dépôt GitHub | à créer par l'utilisateur (privé), voir README étape 1 |
| Site, base, réveil | pas encore mis en ligne au 06/10/2026 (README étapes 2 à 6) |

Variables d'environnement (valeurs dans Render uniquement) : `DATABASE_URL`, `SECRET_KEY` (créée par Render,
ne jamais la changer), `ADMIN_EMAIL`, `CRON_KEY`, `APP_URL`, `APP_NAME`, `GEMINI_API_KEY` (clé commune),
`GEMINI_MODEL`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `SIGNUP_MODE`, `INVITE_CODE`, `CONTACT_EMAIL`, `DONATE_URL`,
`TELEGRAM_TOKEN`, `TELEGRAM_BOT`, `COLLECT_EVERY_SEC`, `LEGAL_NAME`, `PREMIUM_URL`, `PREMIUM_PRICE`, `GA_ID`, `BREVO_API_KEY`, `MAIL_FROM`.

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
- `backend/tests/test_pipeline.py` : tests avec réseau simulé (`python -m pytest -q` dans `backend`).
- `frontend/src/` : `App.jsx` (connexion, offres, suivi, assistant, profil), `Settings.jsx`, `Admin.jsx`, `api.jsx`.

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
  (`COLLECT_PARALLEL`) pour ménager la mémoire de Render. Pistes vérifiées mais non faites : connecteurs Workable
  (`apply.workable.com/api/v1/widget/accounts/XXX`) et Teamtailor (`XXX.teamtailor.com/jobs.rss`), The Muse, Jooble
  et Careerjet (clé à demander). Il n'existe pas de source gratuite couvrant « toutes les entreprises de France ».
  L'utilisateur a demandé d'économiser son quota Claude : pas d'agents de recherche en série.
- 10 tests automatiques réussis. Les derniers lots sont à pousser par l'utilisateur (GitHub Desktop).
- Accès GitHub : seul `ChampionsLeague_DB` est autorisé pour Claude ; l'utilisateur doit ajouter `veille-stages`
  dans les dépôts autorisés pour que la session puisse pousser elle-même.

## Pistes non faites

L'utilisateur vise à terme une vraie application (web puis mobile) rapportant 200 à 300 € par mois. Ordre conseillé :
mesurer l'usage (statistiques dans Administration), puis alternance et toute la France, alertes par e-mail,
vérification d'adresse et mot de passe oublié (demande un service d'envoi d'e-mails), paiement automatique
(Stripe) à la place de l'activation manuelle du Premium, puis application sur les stores.
