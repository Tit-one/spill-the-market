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

1. **Brief :** décrire le produit et sa catégorie, son prix, la tranche d'âge, la population, les jours et le budget publicitaire virtuel. Les budgets d'achat individuels sont des hypothèses synthétiques du modèle.
2. **Préparer :** générer la recherche de démonstration ou analyser des documents importés, puis consulter les profils et leurs sources.
3. **Sources :** choisir documents, pages/RSS ou recherche connectée. Les propositions d'âge montrent leur statut et doivent être appliquées explicitement au brief avant une nouvelle préparation.
4. **Plans média :** éditer les trois prix/stratégies, les canaux, créations, formats, poids budgétaires, horaires et répétitions. Verrouiller les lignes à conserver.
5. **Lancer :** suivre la progression ; annuler puis reprendre si nécessaire. Les résultats engagés et les frais API incertains restent enregistrés.
6. **Comparer :** examiner le CA virtuel, les ventes, l'acquisition, la fatigue, les interactions sociales, les témoins sans campagne et les hypothèses. Télécharger le rapport.

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

[Définitions détaillées](METHODOLOGY.md) · [Mesures de performance](BENCHMARKS.md) · [Preuves de vérification](VERIFICATION.md).

## Lire une page produit

L'onglet **La page** capture une URL publique sur ordinateur/mobile, rend du HTML hors ligne ou importe vos captures. Installer Chromium une fois pour les captures automatiques : `uv run python -m playwright install chromium` ; ajouter `--with-deps` si nécessaire sous Linux.

1. Capturer la page A, et éventuellement B. Vérifier les images locales et la couverture des sections.
2. Choisir le modèle visuel configuré, le nombre borné de personas et le contrôle par lecture directe des images. Pour un fournisseur distant, une autorisation précise est requise et le budget API réel de l'étude doit être positif.
3. Lancer l'analyse : description des régions visibles, lecture progressive des personas, compréhension/questions/confiance/rejet/intention et comparaison appariée. Les captures restent locales tant que l'analyse distante n'est pas autorisée.
4. Exporter les preuves et réactions. La démonstration fictive ne lit pas une vraie page et ne fait aucun appel d'IA.

Les captures automatiques désactivent les scripts : une page dynamique peut être incomplète. Importer des captures prises dans son navigateur pour conserver son rendu. Le HTML importé n'exécute ni scripts ni requêtes réseau. La navigation autonome et le fonctionnement réel du paiement restent ultérieurs. [Configuration et méthode](PAGE-ANALYSIS.md).
