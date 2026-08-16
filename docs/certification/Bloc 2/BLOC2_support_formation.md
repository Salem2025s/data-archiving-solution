# Support de formation — Exploiter le dashboard de gouvernance des données

**Public visé :** analystes de gouvernance et référents métier (non techniciens)
**Durée estimée :** 45 minutes · **Format :** visite guidée pas-à-pas
**Prérequis :** aucun — un simple navigateur web
**Auteur :** HAOUARI Salem · **Projet :** gouvernance et archivage — Oracle PeopleSoft EP92U038

> **Pourquoi cette formation ?** L'outil d'analyse ne crée de la valeur que si vous savez le lire et vous en servir seul. À la fin de cette session, vous saurez naviguer dans le dashboard, comprendre chaque indicateur, reconnaître une classification fiable d'une classification à vérifier, et réutiliser les données dans vos propres outils.

---

## Module 1 — À quoi sert l'outil ? (5 min)

Notre ERP PeopleSoft contient des **dizaines de milliers de tables** aux noms techniques (`PS_JRNL_HEADER`, `PS_JOB`…) que personne ne peut toutes connaître. L'outil répond à trois questions concrètes :

| La question métier | Ce que l'outil donne |
|---|---|
| « Cette table, c'est quel métier ? » | Une **classification automatique** par domaine (Finance, RH, Achats…) |
| « Combien coûte tout ça ? » | Le **coût de stockage**, par domaine |
| « Qu'est-ce que je peux archiver ? » | Une liste **priorisée** de candidats à l'archivage, avec le gain estimé |

**À retenir :** l'outil ne décide pas à votre place. Il **éclaire** la décision avec des chiffres.

---

## Module 2 — Visite guidée du dashboard (10 min)

Le dashboard s'ouvre dans le navigateur. Le menu de gauche donne accès aux pages clés :

1. **Vue d'ensemble** — les grands chiffres du patrimoine (nombre d'actifs, domaines, coût total, économie possible) et la répartition par domaine.
2. **Domaines** — le détail par objet métier : volumétrie, score d'archivage, qualité des données.
3. **Archivage** — les recommandations d'archivage, filtrables par domaine et par stratégie.
4. **Coûts & ROI** — la répartition des coûts et la projection du retour sur investissement.
5. **Console SQL** — pour poser vos propres questions à la base (en lecture seule).

> **Astuce :** le bouton **« Rafraîchir les données »** recharge les chiffres du dernier calcul. Le numéro de *run* affiché en haut à gauche indique quelle exécution vous regardez.

*(Capture : page « Vue d'ensemble » — à insérer.)*

---

## Module 3 — Lire un indicateur sans se tromper (10 min)

Trois indicateurs méritent une explication, car ils sont souvent mal interprétés.

### La répartition par domaine
Elle montre le **poids de chaque métier** dans le patrimoine. Exemple réel : **Finance & Contrôle représente 45 %** des actifs — c'est le domaine sur lequel un effort de gouvernance rapporte le plus.

### La confiance de classification
Chaque table classée reçoit une **confiance**, répartie en trois bandes :

| Bande | Signification | Ce que vous faites |
|---|---|---|
| **High** (élevée) | Le modèle est très sûr | Vous pouvez vous y fier |
| **Medium** (moyenne) | Le modèle penche mais sans certitude | Un coup d'œil recommandé |
| **Low** (faible) | Le modèle hésite | **À vérifier avant toute décision** |

> **Idée fausse à corriger :** « le modèle devrait être sûr à 100 % ». Non — un modèle honnête **affiche son incertitude**. Une confiance *low* n'est pas une erreur, c'est une **alerte utile**.

### Le taux de revue (`review_required`)
Environ **27 %** des actifs sont signalés « à réviser ». C'est **volontaire** : l'outil préfère vous alerter plutôt que de trancher à tort. Ces cas sont votre file de travail prioritaire.

---

## Module 4 — Le réflexe qualité (5 min)

Une seule règle d'or, mais elle est capitale :

> **On n'archive jamais une table sur la foi d'une classification non vérifiée.**

Concrètement, avant de valider une action d'archivage :
1. Vérifiez la **bande de confiance** (les *low* d'abord).
2. Vérifiez le marqueur **`review_required`**.
3. En cas de doute, ouvrez la table dans **Domaines** pour voir ses caractéristiques.
4. Décidez — et tracez votre décision.

Cette prudence protège contre le seul vrai risque du projet : **archiver par erreur une donnée encore utile ou réglementairement sensible.**

---

## Module 5 — Exporter et réutiliser les données (5 min)

Vous n'êtes pas enfermé dans le dashboard :

- **Console SQL** — posez vos questions directement (ex. « toutes les tables Finance de plus de 10 Mo »). L'accès est en **lecture seule** : impossible d'abîmer la base. Vous pouvez télécharger le résultat en CSV.
- **Export Excel** — un classeur de 13 feuilles (profil par domaine, top candidats à l'archivage, coûts, projection ROI…) est disponible pour ceux qui préfèrent travailler sous tableur.

> **Astuce :** dans la Console SQL, filtrez toujours par `run_id` pour comparer des choses comparables.

---

## Module 6 — Bonnes pratiques à emporter (5 min)

- ✓ **Toujours regarder le numéro de run** — un chiffre n'a de sens que rapporté à son exécution.
- ✓ **Traiter les cas *low* et `review_required` en priorité** — c'est là qu'est le risque.
- ✓ **Ne jamais décider d'archiver sur une classification non revue.**
- ✓ **Sourcer les coûts** — les tarifs viennent d'une source externe réelle (API Azure), pas d'une estimation au doigt mouillé.
- ✓ **En cas de doute, demander** — la classification automatique est une aide, pas une autorité.

---

## Pour aller plus loin

- **Documentation technique** (définition et formule de chaque indicateur) : dossier Bloc 2, section C2.3.2, et `docs/E1_gains_stockage/` à `docs/E4_repartition_couts/`.
- **Méthodologie des tests statistiques** : `scripts/bloc2_hypothesis_tests.py`.
- **Questions ?** Contacter l'équipe data-gouvernance.

*Fin du support — merci de votre attention.*
