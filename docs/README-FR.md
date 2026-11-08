# Spill the Market — guide français

Spill the Market est un laboratoire local pour explorer un lancement : marché, personas, prix, communication et achats virtuels.

## Démarrer

Avec Python 3.11/3.12 et uv installés :

```powershell
git clone https://github.com/Tit-one/spill-the-market.git
cd spill-the-market
uv run spill-market serve --open
```

L'application s'ouvre sur **http://127.0.0.1:8765**. Le bouton EN/FR change la langue. Sur Windows, le fichier `Lancer Spill the Market.cmd` lance la même commande. Aucun Docker, compte ou clé API n'est nécessaire pour les deux démonstrations fictives.

## Une étude complète

1. **Choisir l'objectif :** tester une campagne pour une cible connue, ou explorer le marché et ses tranches d'âge.
2. **Décrire le produit :** nom, description, catégorie, prix et budget publicitaire virtuel. En campagne, préciser les âges ; l'exploration utilise une large plage adulte affichée. On peut ajouter la page du produit et des références concurrentes dans **Enrichir avec des sources**.
3. **Lancer :** une seule action prépare les données et les trois stratégies puis démarre le calcul. Suivre la progression, annuler/reprendre si nécessaire et lire le bilan.

Population, jours, répétitions, coûts, stocks et réglages techniques restent dans les options avancées. Les onglets Sources, Personas, Plans média et La page permettent d'approfondir l'étude. Les exemples fictifs se chargent volontairement.

L'exploration présente taux par âge/canal, références concurrentes, freins et migrations simulées depuis une solution existante. Ces migrations sont incluses dans les achats, jamais ajoutées aux ventes. Un classement indépartageable ou un manque de sources reste signalé. [Méthode et limites](MARKET-STUDY.md).

Le type de produit oriente les propositions. Pour un jeu, les autres jeux, Twitch, créateurs et vidéos courtes peuvent être explorés. Le système teste aussi les limites du martelage : attention saturée, fatigue et rejet. Ces mécanismes restent des hypothèses modifiables.

## Bien distinguer les budgets

- **Budget média virtuel :** dépenses publicitaires fictives, identiques entre candidats pour rendre la comparaison lisible.
- **Plafond API réel :** recherche/extraction et enrichissement IA, choisis par l'utilisateur. Le défaut est zéro.

L'option d'enrichissement des représentants nécessite un modèle compatible et un budget positif. Les calculs numériques n'appellent pas une IA pour chaque personne ou chaque journée.

Pour les fournisseurs, utiliser `.env.example` avec les clés et tarifs actuels de son choix puis `spill-market serve --env-file chemin.env`. Ne jamais mettre ce fichier dans Git. Un fichier de configuration MiroFish peut être sélectionné explicitement ; les variables reconnues sont lues en mémoire, sans modification ni copie de ses secrets.

## Mémoire

La mémoire locale SQLite fonctionne sans Zep. Les imports MiroFish sont traités comme données non vérifiées/synthétiques. Un connecteur optionnel Neo4j lit un groupe Graphiti précis ; il ne modifie pas le graphe d'origine et n'exécute pas son extracteur IA.

## Interpréter le rapport

Les personnes et achats sont fictifs. Une intention conditionnelle n'est pas une vente. Les intervalles décrivent la variabilité du modèle, pas la fiabilité d'une future campagne réelle. Les coefficients et prix média par défaut ne sont pas des mesures des plateformes.

La comparaison principale porte sur le **CA total**, avec un budget média commun. Le résultat après coûts reste visible séparément. Un gagnant n'est retenu que si l'écart de validation dépasse le seuil pratique et sa variabilité appariée ; sinon, le rapport indique que les plans sont indépartageables dans l'expérience.

L'accueil commence par un produit vide ; les exemples se chargent volontairement. Les résultats affichent d'abord une conclusion et quatre chiffres d'un scénario nommé : ventes, CA virtuel, dépenses et CAC. Zéro acheteur rend le CAC non calculable. Les trois plans se comparent ensuite ; les détails restent dépliables.

Les promesses extraordinaires non étayées font désormais l'objet d'un triage lexical explicite. Le scepticisme varie entre personnes du même âge, freine l'intention et l'achat et ne disparaît pas sous les rappels. Les commentaires méfiants ne valent pas des recommandations positives. Les coefficients restent des hypothèses ; l'application ne certifie pas l'efficacité d'un produit et ne produit pas de verdict factuel d'arnaque.

En cas de verrouillage Windows temporaire, les écritures atomiques réessaient brièvement. Un échec permanent conserve le dernier état engagé ; **Reprendre le calcul** permet de continuer après résolution. Les rapports de l'ancien modèle restent accessibles avec leur statut non évalué.

[Définitions détaillées](METHODOLOGY.md) · [Mesures de performance](BENCHMARKS.md) · [Preuves de vérification](VERIFICATION.md).

## Lire une page produit

L'onglet **La page** capture une URL publique sur ordinateur/mobile, rend du HTML hors ligne ou importe vos captures. Installer Chromium une fois pour les captures automatiques : `uv run python -m playwright install chromium` ; ajouter `--with-deps` si nécessaire sous Linux.

1. Capturer la page A, et éventuellement B. Vérifier les images locales et la couverture des sections.
2. Choisir le modèle visuel configuré, le nombre borné de personas et le contrôle par lecture directe des images. Pour un fournisseur distant, une autorisation précise est requise et le budget API réel de l'étude doit être positif.
3. Lancer l'analyse : description des régions visibles, lecture progressive des personas, compréhension/questions/confiance/rejet/intention et comparaison appariée. Les captures restent locales tant que l'analyse distante n'est pas autorisée.
4. Exporter les preuves et réactions. La démonstration fictive ne lit pas une vraie page et ne fait aucun appel d'IA.

Les captures automatiques désactivent les scripts : une page dynamique peut être incomplète. Importer des captures prises dans son navigateur pour conserver son rendu. Le HTML importé n'exécute ni scripts ni requêtes réseau. La navigation autonome et le fonctionnement réel du paiement restent ultérieurs. [Configuration et méthode](PAGE-ANALYSIS.md).
