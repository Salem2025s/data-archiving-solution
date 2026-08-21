# BLOC 5 — Support de présentation orale

**Concevoir et déployer des modèles d'apprentissage automatique** — RNCP 39586 (spécialité)
**Candidat :** HAOUARI Salem · **Format :** oral 45 min (30' présentation + 15' échange)
**Projet :** Classification par domaine métier et gouvernance d'archivage — ERP PeopleSoft (Oracle EP92U038)

> **Mode d'emploi.** Chaque section = une slide. « À l'écran » = ce qui s'affiche (sobre). « Ce que je dis » = les notes orales. Les 11 compétences C5.1.1 → C5.3.4 sont couvertes ; une carte de correspondance figure à la fin, suivie d'une préparation aux questions du jury.

---

## Slide 1 — Titre

**À l'écran :**
- **Concevoir et déployer un modèle de classification par domaine métier**
- Cas réel : cartographier 167 260 tables d'un ERP PeopleSoft
- HAOUARI Salem — M2 Expert IA · RNCP 39586

**Ce que je dis (≈30 s) :**
> Je vais vous présenter la conception et le déploiement d'un modèle d'apprentissage automatique qui classe automatiquement les tables d'un ERP par objet métier — de l'analyse du besoin jusqu'au monitoring en production, sur des données réelles.

---

## Slide 2 — Le besoin et le commanditaire *(C5.1.1)*

**À l'écran :**
- Commanditaire : DSI exploitant un ERP PeopleSoft en forte croissance
- Problème : des dizaines de milliers de tables aux noms opaques (`PS_JRNL_HEADER`…)
- Besoin : **savoir automatiquement à quel métier appartient chaque table**
- Contraintes : VPN, RGPD, aucune vérité terrain, produit « base substituable »
- Faisabilité : **prouvée** — pipeline de bout en bout sur données réelles

**Ce que je dis (≈2 min) :**
> Le commanditaire est la DSI d'une organisation dont l'ERP a énormément grossi. Personne ne sait plus rattacher chaque table à un métier — Finance, RH, Achats… Or sans cette carte, impossible de décider quoi archiver. Le besoin est donc une **classification automatique** des tables par domaine. Les contraintes sont fortes : accès VPN en lecture seule, RGPD sur les métadonnées, et surtout **aucune vérité terrain** — personne n'a labellisé ces 167 000 tables. J'ai conclu à la faisabilité en construisant d'abord un pipeline complet qui produit un jeu de données exploitable.

---

## Slide 3 — La stratégie : un problème d'optimisation *(C5.1.2)*

**À l'écran :**
- Angle retenu : **classification supervisée multiclasse** (7 domaines)
- Traduction en optimisation : minimiser une **perte** (log-loss / hinge) sous contrainte de rappel réglementé
- Données à acquérir : nom technique, colonnes, types, volumétrie → **features texte + numériques**
- Amorce du problème « sans label » : labels initiaux **générés par LLM** (consensus ≥ 0,7), puis supervision humaine

**Ce que je dis (≈2 min) :**
> J'ai traduit la question métier « quel domaine ? » en un problème de **classification supervisée à 7 classes**, lui-même un problème d'**optimisation** : trouver les paramètres qui minimisent une fonction de perte, sous une contrainte métier — ne pas rater les domaines réglementés (Finance, RH). Le verrou, c'est l'absence de labels. Je l'ai levé par une amorce : un LLM propose un label par table, je ne garde que les cas de consensus fort (≥ 0,7), ce qui donne un jeu d'entraînement « gold » de 18 473 lignes, que la supervision humaine affine ensuite.

---

## Slide 4 — Les variables : construction du jeu de données *(C5.2.1)*

**À l'écran :**
- Table `processed.dataset_asset_ml` — une ligne par actif
- **Variable cible** : `business_domain` (7 classes)
- **Variables prédictives** :
  - Texte : `technical_name`, `source_ref`, `column_names_text`
  - Numériques : nb de colonnes, taille, ratio de nullables, lignage
- Librairies : **pandas**, scikit-learn (`ColumnTransformer`)

**Ce que je dis (≈2 min) :**
> Le pipeline construit une table plate, une ligne par table de l'ERP. La variable dépendante est le domaine métier. Les variables prédictives combinent du **texte** — le nom technique, les noms de colonnes, très informatifs — et du **numérique** — nombre de colonnes, taille, taux de champs nullables, dépendances. Tout est assemblé avec pandas et un `ColumnTransformer` scikit-learn, qui applique le bon traitement à chaque type.

---

## Slide 5 — La sélection des variables *(C5.2.2)*

**À l'écran :**
- **Réduction de dimension** : TF-IDF plafonné
  - char n-grammes (3-5) sur noms → `max_features = 50 000`
  - word n-grammes (1-2) sur colonnes → `max_features = 80 000`
- **Méthode incorporée (embedded)** : la régularisation du LinearSVC pondère et éteint les features peu utiles
- **Ablation** : comparaison avec/sans groupes de features → gardés seulement s'ils améliorent le F1

**Ce que je dis (≈1 min 30) :**
> Deux mécanismes de sélection. D'abord une **réduction de dimension** : je ne garde que les 50 000 n-grammes de caractères et 80 000 n-grammes de mots les plus fréquents. Ensuite une **méthode incorporée** : le LinearSVC, par sa régularisation L2, attribue lui-même un poids à chaque feature et neutralise les non-informatives. J'ai validé la pertinence des groupes de variables par ablation — on ne garde un groupe que s'il fait monter le F1.

---

## Slide 6 — Sélection des technologies : la comparaison *(C5.1.3, C5.2.4)*

**À l'écran :** (tableau — validation croisée sur le gold)

| Rang | Modèle | Macro-F1 | Accuracy | Temps CV | Famille |
|---|---|---|---|---|---|
| **1** | **LinearSVC + Platt** | **0,869** | 0,907 | **327 s** | Linéaire |
| 2 | LightGBM | 0,867 | 0,909 | 1 020 s | Gradient Boosting |
| 3 | MLP (deep learning) | 0,853 | 0,893 | 1 250 s | Réseau |
| 4 | XGBoost | 0,845 | 0,886 | 3 471 s | Gradient Boosting |
| 5 | LogisticRegression | 0,830 | 0,871 | 413 s | Linéaire |

- Écart 1-2 **non significatif** (p = 0,79) → on tranche sur les **critères opérationnels**

**Ce que je dis (≈3 min) :**
> J'ai comparé cinq familles d'algorithmes en validation croisée sur le jeu gold. Le LinearSVC calibré arrive premier en macro-F1, et surtout il est **trois fois plus rapide** que LightGBM pour une performance statistiquement équivalente — l'écart avec le deuxième n'est pas significatif, p à 0,79. Quand deux modèles sont à égalité, on tranche sur l'opérationnel : simplicité, rapidité, déterminisme, poids de déploiement. C'est ce qui fait gagner le LinearSVC. C'est un point important : **le meilleur modèle n'est pas le plus complexe, c'est celui qui répond le mieux aux contraintes.**

---

## Slide 7 — L'entraînement : deux librairies, deux modèles *(C5.2.3)*

**À l'écran :**
- **Modèle de production** — scikit-learn : `CalibratedClassifierCV(LinearSVC)` + TF-IDF
  - entraînement déterministe, `class_weight=balanced`, `sample_weight=consensus`
- **Modèle avancé** — PyTorch / HuggingFace : **XLM-RoBERTa v3** fine-tuné
  - 50 epochs, *focal loss*, *feature gating*, export **ONNX**
- Les deux produisent des **inférences** sur tables inconnues

**Ce que je dis (≈2 min 30) :**
> J'ai entraîné **deux** modèles avec deux librairies. Le modèle de production, en scikit-learn : un LinearSVC calibré par la méthode de Platt, pondéré par le consensus des labels et par l'équilibre des classes. Et un modèle avancé, en PyTorch via HuggingFace : un **XLM-RoBERTa fine-tuné** sur 50 epochs, avec focal loss pour gérer le déséquilibre et une passerelle de features numériques, exporté en ONNX pour l'inférence. Les deux fonctionnent et prédisent sur des tables jamais vues — je le montre en direct sur le dashboard.

---

## Slide 8 — L'optimisation *(C5.2.4)*

**À l'écran :**
- **Leviers** : data (consensus, équilibrage) · hyperparamètres · fonction de perte
- **Moyens** : validation croisée stratifiée, GPU pour le fine-tuning
- Optimisations clés du XLM-R :
  - *focal loss* → meilleur rappel sur classes rares
  - **calibration** → ECE **0,011** (la confiance devient fiable)
- Comparaison systématique des variantes (v1 → v3)

**Ce que je dis (≈2 min 30) :**
> J'ai optimisé sur trois leviers : la **donnée** (pondération par consensus, équilibrage), les **hyperparamètres** (via validation croisée stratifiée), et la **fonction de perte**. Sur le transformer, deux choix ont compté : la *focal loss*, qui force le modèle à mieux traiter les domaines rares, et surtout la **calibration** — j'ai réduit l'erreur de calibration à 0,011, ce qui veut dire que quand le modèle annonce 90 %, c'est vraiment 90 %. J'ai comparé les versions v1, v2, v3 de façon systématique pour retenir la meilleure.

---

## Slide 9 — L'honnêteté de l'évaluation *(transversal — éthique)*

**À l'écran :**
- Le holdout LLM affiche **89 %** de F1… mais les labels viennent du LLM
- **Justesse réelle validée humainement : ~58-75 %**
- Garde-fou : `review_required` sur 27 % des tables incertaines
- **Je publie le vrai chiffre, pas le chiffre flatteur**

**Ce que je dis (≈2 min) :**
> Un point sur lequel je veux être transparent. Si j'évalue mon modèle contre les labels du LLM, j'obtiens 89 %. Mais ce serait me mentir : le LLM a produit ces labels. Quand je teste contre un gold **humain**, la justesse réelle tombe autour de 58 à 75 %. **Je publie ce chiffre-là.** Et j'ai mis un garde-fou : 27 % des tables, les plus incertaines, sont marquées « à réviser » avant toute décision. C'est ce que j'attends d'un ingénieur ML : mesurer honnêtement, pas gonfler un holdout.

---

## Slide 10 — Sauvegarde et versioning *(C5.3.1)*

**À l'écran :**
- **Sérialisation** : `joblib` (pipeline sklearn) · **ONNX** (transformer)
- **Registre de modèles** (`artifacts/model_registry.json`) : version, métriques, hash SHA-256, commit Git, *stage*
- Une seule version en **production** à la fois ; les autres en *staging* / *archived*
- Réutilisation : `production_pipeline_latest.joblib` chargé par le scoring batch

**Ce que je dis (≈2 min) :**
> Les modèles sont sérialisés — joblib pour le pipeline scikit-learn, ONNX pour le transformer. Et j'ai construit un **registre de modèles** : chaque modèle validé y est enregistré avec sa version, ses métriques, son empreinte SHA-256 et le commit Git qui l'a produit. Le registre garantit qu'une seule version est en production à un instant donné, les autres en staging ou archivées. C'est ce registre qui pilote la promotion en production.

---

## Slide 11 — Déploiement CI/CD *(C5.3.2)*

**À l'écran :**
- **Intégration continue** (`.github/workflows/ci.yml`) : à chaque push
  - lint (ruff) · **tests (pytest, 61 tests)** · garde-fou de régression train/inférence
- **Containerisation** : `Dockerfile` (Python 3.13, user non-root, modèle léger)
- **Registre** : enregistrement automatisable du modèle + promotion
- Modèle de prod = **quelques Mo** → déployable chez un client sans GPU

**Ce que je dis (≈2 min 30) :**
> Le déploiement s'appuie sur une chaîne CI/CD réelle. À chaque push sur `main`, GitHub Actions lance le lint, les 61 tests, et un garde-fou spécifique qui vérifie la parité entre l'entraînement et l'inférence — un bug que j'avais rencontré et que je ne veux plus jamais réintroduire. L'application est containerisée avec un Dockerfile, en utilisateur non-root. Et comme le modèle de production ne pèse que quelques Mo, l'image se déploie chez un client **sans exigence GPU** — c'est décisif pour un produit qu'on veut vendre.

---

## Slide 12 — Monitoring de la performance *(C5.3.3)*

**À l'écran :** (`src/ml/model_reliability.py`)
- **Calibration** : suivi de l'ECE → alerte si > 0,05 sur le gold humain
- **SLA de rappel** par domaine réglementé (Finance, RH, Achats, Ventes) : seuil avant toute action
- **Drift** : à chaque run, snapshot de distribution → alerte si dérive
- Historisé en base, versionné par `run_id`

**Ce que je dis (≈2 min 30) :**
> Un modèle en production se dégrade avec le temps ; il faut le surveiller. J'ai un module de fiabilité qui suit trois signaux. La **calibration** : si l'ECE dépasse 0,05 sur le gold humain, alerte de recalibration. Le **rappel réglementé** : avant d'autoriser un archivage sur un domaine sensible comme la Finance, son rappel doit dépasser un seuil, sinon on bloque. Et la **dérive** : à chaque exécution, je compare la distribution des prédictions à la référence, et je remonte une alerte si ça bouge. Tout est historisé et versionné.

---

## Slide 13 — Automatisation du cycle de vie *(C5.3.4)*

**À l'écran :**
- Orchestration **Prefect** : extraction → features → scoring → publication
- **Historisation des prédictions** : chaque run stocké (`run_id`), comparaison N-1
- **Collecte de nouvelles données** : chaque extraction enrichit le jeu, ré-entraînement possible
- Déploiements cron : collecte nocturne + rafraîchissement horaire

**Ce que je dis (≈2 min) :**
> Le cycle de vie est automatisé par des pipelines Prefect : extraction, construction des features, scoring, publication — enchaînés et tracés. Chaque exécution est **historisée** avec son `run_id`, ce qui permet de comparer d'un run à l'autre et de détecter une évolution. Et chaque extraction **collecte de nouvelles données** qui alimentent un futur ré-entraînement. Deux déploiements cron tournent : la collecte lourde de nuit, le rafraîchissement analytique toutes les heures.

---

## Slide 14 — Le cas d'arbitrage : pourquoi pas le transformer en production ?

**À l'écran :**
- XLM-R : meilleure **calibration** (ECE 0,011) et rappel réglementé
- LinearSVC : meilleure **accuracy** (0,91 vs 0,84), **quelques Mo vs 2,1 Go**, intégré
- Décision : **garder le LinearSVC**, promouvoir le XLM-R *si* une éval humaine équitable le justifie
- « Le meilleur modèle sur le papier n'est pas le meilleur en production »

**Ce que je dis (≈2 min) :**
> On me demande souvent : votre transformer est plus moderne, pourquoi n'est-il pas en production ? Parce que « meilleur » mérite d'être précisé. Le XLM-R est mieux **calibré**, mais le LinearSVC est meilleur en **accuracy** — 0,91 contre 0,84 — pèse quelques Mo contre 2,1 Go, et est déjà intégré. Promouvoir le transformer sur un holdout non validé humainement ne serait pas défendable. Donc je le garde comme axe de recherche, promouvable le jour où une comparaison équitable sur vérité terrain le justifie. C'est un arbitrage d'ingénieur, pas un renoncement.

---

## Slide 15 — Bilan et perspectives

**À l'écran :**
- ✓ De l'analyse du besoin au monitoring : **cycle ML complet**
- ✓ Deux modèles, un registre, une CI/CD, un monitoring — sur données réelles
- ✓ Fil rouge : **l'honnêteté** (perf réelle, arbitrages tracés)
- Perspectives : gold humain élargi, ré-entraînement continu, coffre à secrets

**Ce que je dis (≈1 min 30) :**
> En résumé, j'ai couvert le cycle complet : analyse du besoin, stratégie, données, comparaison de modèles, entraînement de deux modèles, optimisation, sauvegarde avec registre, déploiement CI/CD, monitoring et automatisation — le tout sur un cas réel. Le fil rouge, c'est l'honnêteté : je publie la performance réelle et je trace mes arbitrages. Les perspectives : élargir le gold humain, brancher le ré-entraînement continu, et externaliser les secrets. Je vous remercie.

---

## Slide 16 — Merci

**À l'écran :**
- **Merci — questions ?**
- Dépôt : github.com/Salem2025s/data-archiving-solution

---

## Carte de correspondance avec la grille

| Compétence | Slide(s) |
|---|---|
| C5.1.1 Analyse du besoin | 2 |
| C5.1.2 Stratégie de résolution | 3 |
| C5.1.3 Sélection technologies/algos | 6 |
| C5.2.1 Construire les variables | 4 |
| C5.2.2 Sélection de variables | 5 |
| C5.2.3 Entraînement | 7 |
| C5.2.4 Optimisation | 6, 8 |
| C5.3.1 Sauvegarde / versioning | 10 |
| C5.3.2 Déploiement CI/CD | 11 |
| C5.3.3 Monitoring | 12 |
| C5.3.4 Automatisation cycle de vie | 13 |

---

## Préparation aux 15 minutes d'échange (questions probables)

**Q — « Votre modèle n'est juste qu'à 58 %, à quoi sert-il ? »**
> Il ne décide pas, il **priorise**. Sur 167 000 tables, il concentre l'attention humaine là où elle compte, avec un garde-fou sur les cas incertains. 58 % de départ automatique sur un patrimoine que personne ne savait cartographier, c'est un gain réel — et la boucle de revue humaine fait monter ce chiffre.

**Q — « Pourquoi ne pas déployer le transformer, plus performant ? »**
> Il n'est pas plus performant en accuracy (0,84 vs 0,91) ; il est mieux calibré. Et il pèse 2,1 Go contre quelques Mo. Pour un produit installé chez un client, le modèle léger gagne. (cf. slide 14)

**Q — « Comment garantissez-vous la reproductibilité ? »**
> Versionnement par `run_id`, registre de modèles avec hash et commit Git, CI qui rejoue les tests à chaque push, et un garde-fou de régression train/inférence.

**Q — « Vos labels viennent d'un LLM — n'est-ce pas circulaire ? »**
> Si, et je l'assume : le LLM est une **amorce** d'annotation, pas la vérité. C'est pourquoi je mesure contre un gold **humain** et publie ce chiffre plus bas. La solution vient des règles + supervision humaine, pas du LLM seul.

**Q — « Comment détectez-vous qu'un modèle se dégrade ? »**
> Trois signaux monitorés : ECE (calibration), rappel réglementé (SLA), et drift de distribution à chaque run, avec alertes. (cf. slide 12)

**Q — « Le focal loss, pourquoi ? »**
> Pour le déséquilibre des classes : il baisse le poids des exemples faciles et force le modèle à travailler les domaines rares, ce qui remonte leur rappel — critique pour les domaines réglementés.
