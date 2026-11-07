# Critères de livraison proposés

Date : 7 novembre 2026. Statut : plan validé dans le chat, première version implémentée et qualifiée. Les preuves et leurs limites figurent dans [VERIFICATION.md](docs/VERIFICATION.md).

Référence : [PLAN-A-VALIDER.md](PLAN-A-VALIDER.md).

## Première version

- [x] Installation et tests Windows/Linux/macOS en CI ; application locale, interface embarquée, CLI/API partagés ; contrôle de vrai worker installé sans Node ajouté au dernier cycle CI.
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

## Module 5 ultérieur

- [ ] URL/HTML/captures ; vues mobile/ordinateur et positions de défilement.
- [ ] Observations factuelles structurées et ancrées dans les captures, interprétations séparées.
- [ ] Chaque persona ne voit que les informations accessibles à l'étape de son parcours.
- [ ] Réactions liées à ses besoins, caractéristiques et publicité d'origine.
- [ ] Compréhension, questions, confiance, rejet et intention reliés aux sections déclenchantes.
- [ ] Lecture directe des captures par un échantillon, comparée à la description commune.
- [ ] Comparaison de deux pages avec mêmes profils et conditions.
- [ ] Audit visuel, intention synthétique, navigation fonctionnelle et comportements réels distingués.

Une case exige une preuve actuelle : code, commande, test, capture ou mesure. Un nom de module ou un bouton ne prouve pas son fonctionnement.


Les cases du module5 restent intentionnellement ouvertes : il appartient à la suite explicitement validée, pas à la première livraison.
