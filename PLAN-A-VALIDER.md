# Spill the Market — plan à valider

Date : 7 novembre 2026. Statut : validé explicitement dans le chat le 7 novembre 2026 ; développement en cours.

## Produit

Application open source autonome, locale, avec interface web et CLI Python pour créateurs et entrepreneurs. L'installation MiroFish existante reste intacte. Nom du dépôt envisagé : spill-the-market ; aucune publication effectuée.

## Première version : quatre modules complets

1. Recherche : idée/produit vers tendances, pain points, concurrents, jargon et segments ; modes API, URL/RSS choisis et documents hors ligne. Sources, dates, couverture et hypothèses conservées ; aucune croissance historique inventée.
2. Personas : tranche d'âge stricte ou cible proposée à confirmer, besoins/budgets/habitudes diversifiés ; pas de trait psychologique automatique fondé uniquement sur l'âge. Mémoire locale par défaut, Graphiti/Neo4j optionnel, aucun Zep obligatoire. Faits, croyances fictives et événements simulés séparés.
3. Communication : trois plans média modifiables et verrouillables, adaptés au produit ; fréquence/calendrier/budgets ajustés dans les règles de l'expérience. Canaux : TikTok, Instagram, Facebook, YouTube, Twitch, X, Reddit, communautés, créateurs, publicités dans les jeux (vidéos récompensées, interstitiels et bannières), recherche payante, display, podcasts, newsletters et affiliation. Modèles exécutables distincts pour vidéos courtes, groupes fermés et formats dans les jeux ; paramètres calibrés ou hypothétiques identifiés. Récence, fatigue, saturation et attention partagée entre canaux.
4. Achats : trente jours par défaut ; exposition, attention, intérêt, questions, intention et achat virtuel distingués. Besoin, confiance, prix, moyens, répétition et fatigue font évoluer l'intention. Trois stratégies prix/communication sous même enveloppe ; témoins sans campagne aux prix correspondants. Rapport : unités, acheteurs uniques, CA virtuel, dépenses, commissions, conversions attribuées, CAC et trajectoires quotidiennes. Variabilité de simulation conditionnelle aux hypothèses.

## Module 5 : suite prévue, préparée dans l'architecture initiale

Le moteur visuel complet vient après les quatre modules précédents.

- Entrées : URL, HTML ou captures ; vues mobile/ordinateur, premier écran et sections après défilement.
- Une IA visuelle produit une description factuelle des textes, prix, conditions, boutons, positions et éléments de confiance.
- Observation séparée de l'interprétation ; chaque persona reçoit seulement ce qu'il a déjà découvert.
- Les personas conservent attentes issues de la publicité, besoins, âge et autres caractéristiques individuelles.
- Recueil : compréhension, questions, orientation, confiance, hésitation, rejet et évolution de l'intention.
- Chaque blocage est relié à la section et la capture correspondantes.
- Un échantillon lit directement les captures pour contrôler les pertes de la description commune.
- Comparaison de deux pages avec mêmes profils et conditions initiales.
- Navigation réelle par certains personas dans une évolution supplémentaire ; l'analyse de captures ne prouve pas le fonctionnement des boutons.

## Socle et expérience

Python 3.11/3.12, FastAPI, Pydantic, Typer, NumPy ; React/TypeScript/Vite, interface compilée embarquée. SQLite/FTS5 et relations de graphe par défaut, données actives hors OneDrive. Connecteurs optionnels isolés, imports MiroFish sans charger son application. Démonstrations fictives hors ligne jeu indépendant/logiciel créatif ; anglais/français ; exports JSON, CSV, Markdown et HTML. Clés et données privées exclues du dépôt et des exports.

## Échelle et coûts

Cible : 100 000 états individuels légers distincts avec représentants LLM bornés, sans 100 000 conversations IA simultanées. Capacité annoncée après benchmarks d'une étude complète. Budgets indépendants : publicité virtuelle et services/API réellement facturés, plafonds choisis par l'utilisateur. Réservation avant appel/réessai ; dépense incertaine conservée et signalée après incident.

## Ordre après validation

1. Socle, contrats, mémoire et démonstration reproductible.
2. Quatre modules et tests.
3. Interface guidée et comparaison de bout en bout.
4. Vérification financière, coûts, isolation, annulation et reprise.
5. Mesures 1 000/10 000/100 000 personnes et étude complète ; temps, RAM, disque, appels et matériel documentés.
6. Paquet installable et dépôt GitHub documenté.
7. Module 5 selon la suite ci-dessus.

Première livraison : adultes, application locale, achats/publicités simulés. SaaS, dépenses publicitaires réelles, achats réels et navigation autonome complète hors périmètre initial.

## État actuel

Développement autorisé par la réponse « Oui, commence le développement ». Voir docs/superpowers/plans/2026-11-07-v0.1.md pour le suivi. Dossier local utilisé pour ces documents car la création de fichiers dans le point de réanalyse OneDrive Miro échoue actuellement ; aucune correction des réglages OneDrive effectuée.

Critères de preuve : [CRITERES-DE-LIVRAISON.md](CRITERES-DE-LIVRAISON.md).
