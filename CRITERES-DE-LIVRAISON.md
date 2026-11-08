# Critères de livraison

Date : 8 novembre 2026. Statut : les quatre modules initiaux et le module 5 demandé sont implémentés. Les preuves de qualification, versions et limites figurent dans [VERIFICATION.md](docs/VERIFICATION.md) et les notes de publication.

Référence : [PLAN-A-VALIDER.md](PLAN-A-VALIDER.md).

## Première version

- [x] Installation et tests Windows/Linux/macOS en CI ; application locale, interface embarquée, CLI/API partagés ; vrai worker installé sans Node réussi dans les six configurations Python 3.11/3.12.
- [x] Démonstration des quatre modules, données fictives et réseau désactivé.
- [x] Trois modes de recherche : API, URL/RSS choisis, imports hors ligne ; sources/extraits/dates/couverture/erreurs conservés.
- [x] Sorties JSON versionnées ; faits, déductions et hypothèses distingués ; pas de croissance historique ni de démographie inventée.
- [x] Âges stricts et diversité au sein d'une tranche ; mémoire locale et isolation des expériences.
- [x] Catalogue de canaux demandé présent avec mécanismes réellement exécutés, coûts et plafonds fonctionnels.
- [x] Courtes vidéos, groupes fermés et publicités dans les jeux possèdent des comportements distincts.
- [x] Plans adaptés au produit, éditables/verrouillables ; fréquence, récence, fatigue et saturation affectent les résultats.
- [x] Calendrier exécuté une seule fois, même après reprise.
- [x] Intention conditionnelle séparée des achats ; acquisitions dédupliquées, identité commune entre canaux.
- [x] Trois stratégies, mêmes conditions initiales, budgets comparables et témoins pertinents.
- [x] CA, dépenses, commissions, conversions attribuées et CAC rapprochés avec les traces ; ratios sans dénominateur explicites.
- [x] Exploration et validation distinctes ; versions, paramètres, sources et graines sauvegardés.
- [x] Budgets réels contrôlés entre recherche, génération, rapports, concurrence, réessais et reprise.
- [x] Réservations incertaines conservées après incident ; aucune relance facturable aveugle.
- [x] Annulation/reprise vérifiées ; résultats engagés équivalents à une exécution continue.
- [x] Benchmarks 1 000/10 000/100 000 personnes puis étude complète, avec temps/RAM/disque/appels/matériel documentés.
- [x] URL et redirections contrôlées, entrées traitées comme données, HTML assaini, secrets exclus des sorties publiques.
- [x] MiroFish existant préservé ; imports et connecteur mémoire optionnel vérifiés séparément.
- [x] Documentation anglaise/française, exemples, méthodologie, contribution, notices et exports présents.

## Module 5 — v0.2

- [x] URL/HTML/captures ; vues mobile/ordinateur et positions de défilement.
- [x] Observations factuelles structurées et ancrées dans les captures, interprétations séparées.
- [x] Chaque persona ne voit que les informations accessibles à l'étape de son parcours ; les images longues sont découpées avant exposition.
- [x] Réactions liées à ses besoins, caractéristiques et contexte publicitaire déclaré.
- [x] Compréhension, questions, confiance, rejet et intention reliés aux sections déclenchantes.
- [x] Lecture directe des captures par un échantillon, comparée à la description commune ; contrôles fictifs et appels réels distingués dans les preuves.
- [x] Comparaison de deux pages avec mêmes profils et horizon commun ; couvertures inégales signalées.
- [x] Audit visuel, intention synthétique, navigation fonctionnelle et comportements réels distingués.

Une case exige une preuve actuelle : code, commande, test, capture ou mesure. Un nom de module ou un bouton ne prouve pas son fonctionnement.


La navigation autonome, les clics réels et la vérification d'un paiement restent ultérieurs. Les intentions d'action du lecteur sont enregistrées dans un calendrier d'inspection fixe ; elles ne pilotent pas encore un navigateur.
