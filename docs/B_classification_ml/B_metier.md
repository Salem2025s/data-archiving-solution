# B — Classification ML par objet métier : Fiche Métier

> **Statut :** ✅ Complet  
> **Public cible :** Chef de projet, jury PFE, non-technicien

---

## Qu'est-ce qu'on fait dans cette section ?

On **classe automatiquement chaque table de la base Oracle** dans un domaine métier : Finance, RH, Achats, IT, Supply Chain, Ventes & Clients, ou Other.

Sur les 167 263 assets analysés, **100 % sont classifiés** — sans intervention humaine.

---

## Pourquoi c'est un défi ?

Une base ERP comme PeopleSoft contient des milliers de tables avec des noms techniques cryptiques (ex. : `VCHR_ACCTG_LINE`, `PSACCESSLOG`, `IN_DEMAND`). Sans classification, il est impossible de :
- Savoir à quel service appartient une table
- Prioriser les décisions d'archivage par domaine métier
- Produire des KPI par département (Finance a-t-elle plus de données que les RH ?)

---

## Comment fonctionne la classification ? (version simplifiée)

### Étape 1 — Les règles de mots-clés (26,6 % des assets)

Le système reconnaît des mots-clés caractéristiques par domaine :
- Si une table s'appelle `VOUCHER_LINE` et contient des colonnes comme `AMOUNT`, `VENDOR_ID`, `DUE_DT` → **Finance & Contrôle** (mots-clés : voucher, amount, vendor)
- Si une table s'appelle `PERSONAL_DATA` avec `EMPLID`, `BIRTHDATE` → **RH** (mots-clés : emplid, personal)

Cette étape est rapide et très fiable (confiance = 95 %) pour les tables avec un nom explicite.

### Étape 2 — Le modèle de Machine Learning (73,4 % des assets)

Pour les tables au nom moins évident, un modèle de ML analyse :
- Les caractères qui composent le nom technique (ex. : `VCHR` = souvent Finance)
- Les noms de colonnes de la table (ex. : une table avec beaucoup de colonnes `DATE`, `AMOUNT` ressemble à de la Finance)
- Les statistiques de la table (nombre de colonnes, taille, etc.)

Le modèle a été entraîné sur **18 473 tables étiquetées par IA** (voir plus bas), puis **affiné avec 1 130 tables corrigées à la main** (annotation active sur les cas difficiles).

---

## Les 7 domaines métier

*(Répartition du modèle déployé v3.4-human sur les 167 260 assets du run 6.)*

| Domaine | Exemples de tables PeopleSoft | Part dans la base |
|---|---|---|
| **Finance & Contrôle** | VOUCHER, LEDGER, BUDGET_HDR, PROJECT | 45,1 % |
| **IT & Sécurité** | PSOPRDEFN, ROLEDEFN, PERMISSIONLIST | 21,1 % |
| **Supply Chain** | INV_ITEMS, IN_DEMAND, MASTER_ITEM_TBL | 13,1 % |
| **Achats & Fournisseurs** | PO_HDR, VENDOR, RECV_HDR | 8,6 % |
| **Ventes & Clients** | CUSTOMER, ORDER_HDR, BI_HDR | 6,6 % |
| **Other** | Tables de configuration, métadonnées système | 2,8 % |
| **RH** | PERSONAL_DATA, JOB, COMPENSATION | 2,7 % |

---

## Comment interpréter la confiance ?

Chaque classification est accompagnée d'un niveau de confiance :

| Bande | Signification | Action recommandée |
|---|---|---|
| **High** (≥ 85 %) | Le modèle est très sûr | Accepter la classification |
| **Medium** (60–85 %) | Raisonnablement sûr | Vérification optionnelle |
| **Low** (< 60 %) | Incertain | Revue recommandée (`review_required`) |

> Cette confiance est **calibrée** : on a vérifié sur un échantillon validé humainement que les prédictions « high » sont justes ~70 % du temps contre ~52 % pour les « low » — le niveau de confiance est donc un bon guide pour le tri.

---

## Comment la base d'entraînement a-t-elle été créée ? (annotation par IA)

Pour entraîner un modèle, il faut d'abord des **exemples étiquetés** : des tables dont on connaît déjà le domaine. Annoter des milliers de tables à la main prendrait des semaines.

**Solution retenue :** on a utilisé une **IA générative open-source comme annotateur automatique**.

| Étape | Ce qui a été fait | Chiffre |
|---|---|---|
| 1. Échantillon | On a tiré des tables représentatives de la base | **20 000** |
| 2. Annotation par IA | Chaque table soumise à **Qwen 2.5 (32 milliards de paramètres)**, IA open-source en local, qui propose un domaine + une justification, via **plusieurs votes** (score d'accord = « consensus ») | — |
| 3. Filtre qualité | On ne garde que les tables où les votes sont d'accord (consensus ≥ 0,7) ; les cas douteux partent en revue humaine, les « pile ou face » sont écartés | **18 473** gardées (92 %) |
| 4. Entraînement | Cette base fiable sert à entraîner le modèle de production | 18 473 lignes |

> Sur les 20 000 tables annotées, **18 473 (92 %)** avaient un consensus suffisant pour l'entraînement. Seulement **2** ont nécessité une revue humaine, et **1 525 (8 %)** ont été écartées (votes contradictoires). La base est donc **quasi intégralement étiquetée par l'IA, avec un haut niveau d'accord**.

**Pourquoi c'est malin :**
- L'IA générative **comprend le sens** des noms techniques abrégés (ex. : « VCHR_ACCTG_LINE » → Finance), là où de simples règles échouent.
- On obtient des milliers d'exemples étiquetés **en quelques heures** au lieu de semaines.
- Le modèle final est **1000× plus léger** que l'IA annotatrice : on a en quelque sorte « transféré » le savoir de la grosse IA vers un petit modèle rapide et déployable (technique dite de **distillation**).

> En résumé : une grosse IA (Qwen 32B) a servi de « professeur » pour étiqueter les données, et un petit modèle rapide (le modèle de production) a appris de ces étiquettes.

---

## Quel modèle a été choisi, et pourquoi ?

On a comparé **6 algorithmes** (régression logistique, SVM linéaire, forêt aléatoire, réseau de neurones, LightGBM, XGBoost) sur le même jeu de données, avec validation croisée et test statistique.

**Résultat :** deux modèles sortent en tête, à égalité statistique (différence non significative) :

| Modèle | Qualité (Macro-F1) | Particularité |
|---|---|---|
| **LinearSVC + Platt** ✅ *(retenu)* | 0,869 (meilleur) | Très rapide, donne un % de confiance fiable |
| LightGBM | 0,867 | Aussi performant, mais 3× plus lent et moins transparent |

**Modèle retenu pour la production : LinearSVC + Platt.** À performance équivalente, il a été choisi parce qu'il est :
- **Très rapide** : classe les 167 000 tables en quelques secondes
- **Fiable sur la confiance** : son % de certitude est calibré (un « 80 % » signifie vraiment 80 %)
- **Transparent** : on peut expliquer ses décisions

**LightGBM** reste le « plan B » si on veut un jour pousser la précision au maximum.

Les autres modèles (XGBoost, régression logistique, forêt aléatoire) sont **statistiquement inférieurs** et n'ont pas été retenus. Le **Deep Learning** (réseau de neurones) n'apporte pas d'avantage ici — il sera réévalué dans une future version avec des modèles de langage (BERT).

---

## Quelle est la VRAIE qualité du modèle ? (validation humaine)

Le modèle ayant été entraîné sur des étiquettes produites par une IA, mesurer sa qualité contre ces mêmes étiquettes serait **circulaire** (on ne mesurerait que l'accord avec l'IA, pas la justesse réelle). Pour avoir un chiffre honnête, on a constitué un **jeu de test annoté à la main**.

**Démarche d'apprentissage actif (3 vagues d'annotation ciblée) :**

| Vague | Lignes annotées | Cible | Justesse réelle (cas difficiles) |
|---|---|---|---|
| Modèle initial (IA seule) | 0 | — | **~51 %** |
| + Vague 1+2 | 783 | classes rares + faible confiance | **~61–74 %** |
| **+ Vague 3 (déployé v3.4)** | **1 130** | zone de désaccord | **~75 %** |

À chaque vague, on annote en priorité les tables où le modèle est **le plus incertain** (faible confiance) ou là où l'ancienne et la nouvelle version **ne sont pas d'accord** — ce sont les exemples les plus instructifs. Résultat : **chaque lot de ~500 corrections humaines fait gagner ~13 points** de justesse sur les cas difficiles, sans dégrader le reste.

**Enseignements clés (honnêtes, pour le jury) :**
- Le score « 89 % » souvent cité ne mesure que l'accord avec l'IA annotatrice — la **vraie justesse métier de départ était ~51 %**.
- Le levier le plus efficace n'est **pas** de changer d'algorithme (LightGBM ≈ LinearSVC) mais d'**ajouter des corrections humaines** ciblées.
- La confiance calibrée permet d'**automatiser les cas sûrs** et de **router les cas douteux** vers une revue humaine — pipeline exploitable en l'état.

> Outils livrés : génération d'échantillon à annoter, évaluation humain-vs-modèle, et ré-entraînement reproductible intégrant les corrections (`src/ml/`).

---

## Ce que ça apporte au projet

1. **Gouvernance par domaine** : on connaît la répartition des tables et du volume par domaine métier
2. **Archivage ciblé** : les décisions d'archivage peuvent être proposées domaine par domaine (ex. : "quelles tables Finance de plus de 10 Mo et sans dépendances sont archivables ?")
3. **Reporting** : les KPI de coût et de ROI peuvent être déclinés par domaine métier
4. **Priorisation** : on peut identifier les domaines les plus "lourds" en termes de stockage

---

## Limites et perspectives

- **« Other » fortement réduit** : de 11 % à **2,8 %** grâce aux corrections humaines (le modèle initial sur-utilisait ce fourre-tout). On peut le réduire encore avec d'autres vagues d'annotation.
- **Justesse perfectible (~75 % sur cas durs)** : la boucle d'apprentissage actif n'a pas saturé — d'autres lots ciblés continueraient de l'améliorer.
- **Boucle de supervision humaine en place** : les assets en faible confiance / `review_required` sont revus, et leurs corrections **réintégrées au ré-entraînement** (processus déjà rodé et reproductible).
- **Le modèle n'est pas statique** : ré-entraînable à tout moment sur de nouvelles données labélisées via `src/ml/train_production_classifier.py`.
