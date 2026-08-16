# BLOC 3 — Élaborer et piloter un projet data

**Titre visé :** Ingénieur en science des données spécialisé en infrastructure data ou en apprentissage automatique — **RNCP 39586** (Niveau 7)
**Candidat :** HAOUARI Salem · **Date :** 29/07/2026
**Projet :** Solution de gouvernance et d'archivage intelligent des données d'un ERP PeopleSoft (Oracle EP92U038)
**Dépôt de code :** https://github.com/Salem2025s/data-archiving-solution

> **Note de lecture pour le jury.** Chaque section correspond à une compétence du bloc (C3.1.1 → C3.4.2) : elle présente le livrable attendu puis se termine par un encadré « Critères couverts » reprenant les exigences de la grille. **Précision de périmètre honnête :** le projet de fin d'études a été mené **en solo**. Pour les compétences de gestion d'équipe (C3.3), je distingue clairement ce qui relève du **projet réalisé** (solo, plusieurs casquettes) et ce que je **conçois pour le scénario de mise en production** chez un client — une équipe cible réaliste. Je ne prête jamais au passé une équipe qui n'a pas existé.

---

## Sommaire

1. Contexte et présentation du projet
2. **C3.1 — Cadrer et dimensionner**
   - C3.1.1 Cadrage du projet
   - C3.1.2 Dimensionnement du projet
   - C3.1.3 Documentation projet
3. **C3.2 — Planifier et suivre**
   - C3.2.1 Planning et méthodologie
   - C3.2.2 Suivi de l'avancement
4. **C3.3 — Constituer et piloter l'équipe (scénario de déploiement)**
   - C3.3.1 Plan de développement des compétences
   - C3.3.2 Outils de communication et managériaux
   - C3.3.3 Cas d'arbitrage rencontré
5. **C3.4 — Veiller et agir de façon responsable**
   - C3.4.1 Méthodologie de veille
   - C3.4.2 Plan d'actions RSE, sécurité, éthique et confidentialité
6. Conclusion

---

## 1. Contexte et présentation du projet

Le projet vise à doter une organisation exploitant un ERP **Oracle PeopleSoft** (instance `EP92U038`) d'une solution capable de **cartographier son patrimoine de données par objet métier, d'en chiffrer le coût et de recommander une stratégie d'archivage** justifiée et auditable. La solution est pensée comme un **produit réutilisable**, déployable chez de futurs clients par simple substitution de la source.

Ce bloc ne traite pas de la technique (couverte aux Blocs 1, 2 et 5) mais de la **conduite du projet** : comment il a été cadré, dimensionné, planifié, suivi, et comment les décisions, la veille et les enjeux responsables ont été gérés.

---

## 2. C3.1 — Cadrer et dimensionner

### C3.1.1 — Cadrage du projet

**Livrable : le cadrage du projet.**

#### Problématique

La base de l'ERP grossit sans cartographie à jour : on ne sait ni ce qu'elle contient par métier, ni ce qui coûte, ni ce qui peut être archivé sans risque. La problématique : *cartographier automatiquement le patrimoine, en mesurer le coût par objet métier et recommander une stratégie d'archivage fiable, sans mettre en péril l'intégrité du SI ni la conformité légale.*

#### Objectifs et livrables

| Objectif | Livrable produit |
|---|---|
| Collecter et structurer les métadonnées de l'ERP | Pipeline ETL + entrepôt PostgreSQL médaillon (Bloc 1) |
| Classer automatiquement les tables par domaine métier | Classifieur ML + scoring en base (Bloc 2 / Bloc 5) |
| Chiffrer coûts et ROI, recommander l'archivage | Dashboard décisionnel + export Excel (Bloc 2) |
| Sécuriser la chaîne | Chiffrement PII, moindre privilège, lecture seule (Bloc 1) |

#### Cadre réglementaire

Le projet manipule des métadonnées pouvant contenir des données personnelles (identifiants d'opérateurs, emails dans les logs). Il est soumis au **RGPD** : principes de **minimisation** (on ne collecte que des métadonnées, jamais le contenu métier) et de **protection par défaut** (masquage PII, chiffrement au repos). Les **durées légales de rétention** encadrent les recommandations d'archivage.

#### Contraintes et points de vigilance

- **Technique** : source accessible uniquement par VPN ; aucune écriture sur l'ERP ; volume élevé (>160 k actifs).
- **Données** : noms de tables opaques ; absence de vérité terrain (labels générés par LLM, justesse réelle à valider humainement).
- **Produit** : la solution doit rester générique (base substituable) pour être vendable.
- **Point de vigilance majeur** : ne jamais recommander l'archivage d'une donnée mal classée → nécessité d'un garde-fou humain (`review_required`).

#### Enjeux RSE

Le projet a un **impact environnemental positif intrinsèque** : déplacer des données inactives du stockage « chaud » vers l'archive réduit la consommation énergétique (rapport de coût ×9,8, corrélé à la consommation). Il porte aussi un enjeu **éthique** (ne pas surévaluer la performance d'un modèle IA) et de **confidentialité** (RGPD). Ces enjeux sont détaillés en C3.4.2.

> **Critères couverts (C3.1.1).** Le cadrage identifie **la problématique** (cartographier, chiffrer, archiver sans risque), **les objectifs et livrables** (pipeline, classifieur, dashboard, sécurisation), **le cadre réglementaire** (RGPD : minimisation, protection par défaut, rétention légale), **les contraintes et points de vigilance** (VPN, absence de vérité terrain, garde-fou humain) et **les enjeux RSE** (réduction énergétique de l'archivage, éthique IA, confidentialité).

---

### C3.1.2 — Dimensionnement du projet

**Livrable : le dimensionnement du projet.**

Je distingue le **projet réalisé** (prototype, solo) du **scénario de mise en production** (déploiement client, équipe).

#### Ressources humaines

| Phase | Projet réalisé (prototype) | Scénario de déploiement client |
|---|---|---|
| Rôles | 1 personne, plusieurs casquettes (data engineer, ML engineer, data analyst) | Équipe cible de 3-4 : chef de projet data, data engineer, ML engineer, analyste métier |
| Charge | ~2 mois-homme (juin-juillet 2026) | ~4-6 mois-équipe pour une industrialisation |

#### Ressources matérielles et logistiques

- **Poste de développement** unique (Python 3.13, Docker Desktop).
- **Entrepôt** : PostgreSQL 16 en conteneur Docker (local, gratuit).
- **Source** : accès VPN à l'instance Oracle (fournie).
- **Outils** : tous **open-source** (Python, PostgreSQL, Prefect, Streamlit, scikit-learn) → **coût de licence nul**.
- **Modèle DL** : entraînement XLM-R sur GPU (ponctuel, mutualisable).

#### Chiffrage (coût et délai)

Au stade prototype, le coût est essentiellement **humain** : ~2 mois-homme, l'infrastructure étant open-source et locale (coût marginal). Pour un déploiement client, le chiffrage indicatif : ~4-6 mois-équipe + une infrastructure d'hébergement modeste (le modèle de production LinearSVC pèse quelques Mo, pas d'exigence GPU en inférence batch). **Délai réalisé du prototype : 8 semaines** (2 juin → fin juillet 2026).

#### Analyse de faisabilité

La faisabilité est **démontrée** : le prototype fonctionne de bout en bout sur des données réelles (167 260 actifs classés, coûts et ROI calculés, sécurité opérationnelle). Les risques identifiés — dépendance VPN, absence de vérité terrain — sont documentés et assortis de mesures (résilience réseau, garde-fou humain). Le choix d'outils open-source et d'un modèle de production léger garantit la **transposabilité** chez un client.

> **Critères couverts (C3.1.2).** Le dimensionnement comporte **les ressources humaines** (solo réalisé vs équipe cible 3-4), **les ressources matérielles et logistiques** (poste, Docker/PostgreSQL, VPN, outils open-source), **un chiffrage coût/délai** (~2 mois-homme réalisés en 8 semaines ; ~4-6 mois-équipe pour l'industrialisation) et **une analyse de faisabilité** (prototype fonctionnel sur données réelles, risques maîtrisés, transposabilité assurée).

---

### C3.1.3 — Documentation projet

**Livrable : la documentation projet.**

Le projet est documenté de façon à s'adresser à **deux publics distincts**, ce qui répond directement à l'exigence d'un vocabulaire compréhensible par les parties prenantes.

#### Une documentation à deux registres

Chaque grande fonction du projet est documentée en **deux versions** :
- une version **métier** (`*_metier.md`) — vocabulaire accessible aux décideurs et référents métier ;
- une version **technique** (`*_technique.md`) — détails d'implémentation pour les développeurs.

| Document | Public | Rôle |
|---|---|---|
| `README.md`, `docs/INDEX.md` | Tous | Point d'entrée, installation, lecture critique honnête |
| `docs/A_…` à `docs/E4_…` (métier + technique) | Métier / Dev | Spécifications fonctionnelles et techniques par fonction |
| `docs/certification/BLOC1/2/3` | Jury / management | Dossiers de synthèse |
| `artifacts/production_model_card.md` | Data scientists | Fiche modèle (source de vérité sur le modèle déployé) |
| `docs/PRODUCTION_READINESS.md` | Management | Évaluation de maturité (feux tricolores) |

Cette structure fait office de **cahier des charges vivant** : les spécifications fonctionnelles (quoi) et techniques (comment) sont versionnées avec le code, donc toujours à jour.

> **Critères couverts (C3.1.3).** La documentation projet **présente l'ensemble des caractéristiques du projet** (spécifications fonctionnelles et techniques, fiche modèle, évaluation de maturité) et **est en adéquation avec le cadrage**. Elle est **rédigée dans un vocabulaire compréhensible par les parties prenantes** grâce au double registre systématique métier / technique.

---

## 3. C3.2 — Planifier et suivre

### C3.2.1 — Planning et méthodologie

**Livrable : le planning projet.**

#### Choix de la méthodologie : Kanban

J'ai conduit le projet en **Kanban** (flux continu), et non en Scrum. **Justification** : un projet exploratoire de data science, mené en solo, voit ses priorités évoluer au fil des découvertes (ex. le score d'archivabilité s'est révélé dégénéré, imposant une réorientation). Le flux continu du Kanban — *à faire → en cours → fait*, avec limitation du travail en cours — épouse cette réalité mieux que des sprints time-boxés, dont les rituels (daily, review, rétro) sont surdimensionnés pour une personne. **Bénéfices attendus** : visualisation permanente de l'avancement, souplesse de repriorisation, réduction du travail en cours simultané.

L'outil de planification est un **tableau Kanban** jalonné par les échéances de certification, cohérent avec la méthodologie (flux + jalons), et matérialisé dans le suivi Git.

#### Découpage en phases (planning réel, issu de l'historique Git)

Le planning ci-dessous est **authentique** : il est reconstruit à partir des dates de commits réelles.

| Phase | Période | Contenu |
|---|---|---|
| **P0 — Socle & collecte** | 02/06 | Pipeline initial, collecte Oracle, socle de tests, récit honnête |
| **P1 — Analyse & valorisation** | 03/06 | Comparaison N-1, ROI Monte-Carlo (E2/E3) |
| **P2 — Sûreté & fiabilité** | 05/06 | Fail-safe, audit trail, masquage PII ; calibration, SLA rappel, drift |
| **P3 — Deep Learning** | 19/06 | Fine-tuning XLM-R v1/v3, page de test interactif |
| **P4 — Sécurité & externalisation** | 17/07 | API Azure, scraping, pgcrypto, rôles, refonte dashboard |
| **P5 — Certification** | 07-08/26 | Dossiers Bloc 1, 2, 3, 5 |

#### Répartition des activités (RACI — scénario de déploiement)

Pour l'industrialisation en équipe, je propose la matrice **RACI** suivante (R=Réalise, A=Approuve, C=Consulté, I=Informé) :

| Activité | Chef de projet | Data engineer | ML engineer | Analyste métier |
|---|---|---|---|---|
| Cadrage & specs | A | C | C | R |
| Collecte / ETL | I | **R** | C | I |
| Modélisation ML | A | C | **R** | C |
| Dashboard & restitution | I | C | I | **R** |
| Sécurité & conformité | A | **R** | I | C |
| Recette & validation métier | A | I | I | **R** |

#### Prise en compte des personnes en situation de handicap

Le planning intègre l'accessibilité dès la conception : le livrable de restitution (dashboard) applique des règles d'**accessibilité visuelle** (couleur jamais seule porteuse d'information, contrastes élevés, cf. Bloc 2), et les postes de l'équipe cible sont prévus **aménageables** (matériel adapté, temps supplémentaire pour les tâches concernées).

#### Points de vigilance

- **Chemin critique** : la disponibilité du VPN conditionne toute extraction Oracle — un blocage réseau gèle la collecte. Mesure : résilience réséau (retry, keepalive) et découplage (la couche analytique se recalcule sans VPN).
- **Compétence rare** : le fine-tuning de transformers (XLM-R) est une compétence spécialisée, point de fragilité si portée par une seule personne. Mesure : documentation + montée en compétences (C3.3.1).

> **Critères couverts (C3.2.1).** **Le choix de la méthodologie (Kanban) est justifié** avec ses bénéfices (souplesse, visualisation, limitation du travail en cours) ; **l'outil (tableau Kanban jalonné) est compatible** avec elle. **Le planning est découpé en phases** (P0→P5, dates Git réelles) et **permet de visualiser les phases** (collecte, analyse, restitution). **Les tâches sont assignées selon les compétences (matrice RACI)** et **tiennent compte des personnes en situation de handicap** (accessibilité, postes aménageables). **Les points de vigilance sont soulignés** (chemin critique VPN, compétence rare transformer).

---

### C3.2.2 — Suivi de l'avancement

**Livrable : un outil de suivi de projet et un tableau de bord.**

Le suivi s'appuie sur **trois outils complémentaires**, cohérents avec le Kanban.

#### Outils de suivi

1. **Git** — journal exhaustif de l'avancement (27 commits datés, messages structurés `feat/fix/docs`), qui matérialise le flux Kanban (chaque commit = une carte terminée).
2. **`admin.pipeline_run`** — table de traçabilité des exécutions du pipeline (run_id, flow, statut `success`/`failed`, horodatages début/fin) : suivi opérationnel des traitements.
3. **Dashboard Streamlit** — tableau de bord vivant des indicateurs métier et de l'historique des runs.

#### Indicateurs de suivi (argumentés)

| Indicateur | Type | Ce qu'il pilote |
|---|---|---|
| Nb de commits / phase | Quantitatif | Avancement du développement |
| Statut des runs (`success`/`failed`) | Quantitatif | Santé opérationnelle du pipeline |
| Couverture de classification (% classés) | Quantitatif | Complétude de l'analyse |
| Taux de revue (`review_required`) | Qualitatif | Qualité / fiabilité des résultats |
| Macro-F1, ECE (calibration) | Quantitatif | Performance et fiabilité du modèle |
| Dérive (drift monitoring) | Qualitatif | Anticipation d'une dégradation |

**Argumentation** : ces indicateurs couvrent les trois dimensions attendues — **avancement** (commits, couverture), **respect des délais** (phases datées, jalons de certification) et **maîtrise des coûts/qualité** (taux de revue, performance modèle). Le mélange qualitatif/quantitatif évite de piloter sur les seuls chiffres : le taux de revue, qualitatif, alerte sur un risque que l'accuracy seule masquerait.

> **Critères couverts (C3.2.2).** **L'outil de suivi (Git + `admin.pipeline_run` + dashboard) permet de piloter le projet** en cohérence avec le Kanban. **Le choix des indicateurs qualitatifs et quantitatifs est argumenté** (avancement, santé opérationnelle, qualité, performance, dérive). Ils **permettent de suivre l'avancement, le respect des délais et la maîtrise des coûts/qualité**.

---

## 4. C3.3 — Constituer et piloter l'équipe (scénario de déploiement)

> **Rappel de périmètre.** Le projet a été réalisé en solo. Les livrables de cette section sont **conçus pour le scénario de mise en production** chez un client, où la solution serait portée par une équipe. Ils démontrent la compétence sans réécrire l'histoire du prototype.

### C3.3.1 — Plan de développement des compétences

**Livrable : un plan de développement des compétences.**

#### Compétences à mobiliser

Le déploiement de la solution mobilise quatre familles de compétences : **ingénierie de données** (SQL, ETL, Oracle/PostgreSQL), **machine learning** (classification, calibration, transformers), **analyse & restitution** (dataviz, statistiques) et **sécurité/conformité** (RGPD, chiffrement, moindre privilège).

#### Grille d'évaluation des compétences

| Compétence | Niveau actuel (équipe type) | Niveau requis | Écart |
|---|---|---|---|
| SQL / modélisation | Confirmé | Confirmé | — |
| ETL / orchestration (Prefect) | Intermédiaire | Confirmé | Modéré |
| ML classique (scikit-learn) | Confirmé | Confirmé | — |
| **Deep Learning (transformers)** | Débutant | Confirmé | **Fort** |
| Sécurité / RGPD | Intermédiaire | Confirmé | Modéré |
| Dataviz / restitution | Intermédiaire | Confirmé | Modéré |

**Commentaire** : l'écart critique est le **deep learning** (fine-tuning de transformers) — compétence rare identifiée comme point de vigilance (C3.2.1).

#### Plan de développement et formations préconisées

| Écart | Action de formation | Modalité |
|---|---|---|
| Deep Learning | Formation transformers/HuggingFace + pair-programming sur le modèle XLM-R | En ligne + mentorat interne |
| ETL avancé | Montée en compétences Prefect (déploiements, orchestration) | Documentation + atelier |
| Sécurité / RGPD | Sensibilisation RGPD + revue avec un juriste | Atelier + accompagnement juridique |

#### Prise en compte du handicap

Les modalités de formation sont **adaptées aux situations de handicap** : supports accessibles (contraste, sous-titrage des webinars), **temps supplémentaire** pour les évaluations, aménagement matériel du poste (écran adapté, périphériques ergonomiques).

> **Critères couverts (C3.3.1).** **Les compétences à mobiliser sont identifiées** (data engineering, ML, analyse, sécurité). **Une grille d'évaluation compétences actuelles / à acquérir est commentée** (écart critique : deep learning). **Un plan de développement adapté est établi** avec **des formations préconisées** selon les besoins et profils. **Les modalités prennent en compte le handicap** (supports accessibles, temps supplémentaire, aménagement matériel).

---

### C3.3.2 — Outils de communication et managériaux

**Livrable : les outils de communication et managériaux utilisés.**

#### Répartition équilibrée de la charge

La charge est répartie via la matrice RACI (C3.2.1) : chaque membre porte un domaine principal (R) tout en étant consulté (C) sur les interfaces, évitant à la fois la surcharge d'une personne et les silos.

#### Outils collaboratifs et routines managériales

| Outil / routine | Usage | Justification |
|---|---|---|
| **Git + revue de code** | Collaboration technique, qualité | Traçabilité, revue par les pairs, historique partagé |
| **Tableau Kanban** | Visualisation du flux de travail | Cohérent avec la méthodologie ; charge visible de tous |
| **Stand-up court (async)** | Point d'avancement quotidien | Léger, adapté à une équipe distribuée |
| **Revue de jalon** | Validation de fin de phase | Décision collégiale, alignement |
| **Documentation partagée** (`docs/`) | Référentiel commun | Onboarding rapide, source de vérité unique |

#### Contexte multiculturel et international

Une équipe data est fréquemment **distribuée et internationale**. Les mesures : **documentation et messages de commit en langue partagée**, communication **asynchrone** privilégiée (respect des fuseaux horaires), et **routines écrites** (comptes rendus) plutôt que réunions synchrones systématiques, pour ne pénaliser personne.

#### Prise en compte du handicap

L'intégration prévoit un **poste de travail adapté** et des outils collaboratifs **accessibles** (compatibilité lecteurs d'écran, contrastes), afin de garantir la pleine participation de chacun.

> **Critères couverts (C3.3.2).** **La charge de travail est répartie de manière équilibrée** (RACI, un domaine par membre). **Les outils collaboratifs et routines managériales sont détaillés et justifiés** (Git/revue, Kanban, stand-up async, revues de jalon, doc partagée) et **garantissent le bon fonctionnement de l'équipe**. **Le contexte multiculturel/international est intégré** (async, langue partagée, écrit). **Les personnes en situation de handicap sont prises en compte** (poste adapté, outils accessibles).

---

### C3.3.3 — Cas d'arbitrage rencontré

**Livrable : la présentation d'un cas d'arbitrage rencontré au cours du projet.**

Ce cas est **réel** et a été tranché durant le projet.

#### La problématique nécessitant un arbitrage

Le projet dispose de **deux classifieurs** : un modèle de production **LinearSVC calibré** (scikit-learn, TF-IDF) et un modèle **deep-learning XLM-RoBERTa v3** fine-tuné. La question : *faut-il promouvoir le transformer en production à la place du LinearSVC ?* **Conséquences potentielles** d'un mauvais choix : promouvoir un modèle plus lourd sans gain réel (coût, complexité), ou au contraire ignorer un meilleur modèle (perte de qualité).

#### Les options possibles

| Option | Avantages | Inconvénients |
|---|---|---|
| **A — Promouvoir XLM-R** | Meilleure calibration (ECE 0,011), meilleur rappel réglementé | Accuracy inférieure (0,84 vs 0,91) ; **2,1 Go** à déployer ; non intégré au batch |
| **B — Garder LinearSVC** | Meilleure accuracy/F1 ; **quelques Mo** ; déterministe ; déjà intégré | Calibration moins fine |
| **C — Hybride** | Combiner forces | Complexité de maintenance doublée |

#### La décision, argumentée

**J'ai retenu l'option B (garder le LinearSVC en production)**, pour trois raisons : (1) sur la métrique qui compte — l'accuracy — le LinearSVC **devance** le transformer (0,91 vs 0,84) ; (2) le coût de déploiement du transformer (2,1 Go + runtime ONNX) est disproportionné pour un produit « base substituable » installé chez un client ; (3) les deux modèles étant évalués contre des labels LLM, **promouvoir le transformer sur un holdout non validé humainement ne serait pas justifiable**. Le XLM-R reste développé comme axe de recherche (Bloc 5), promouvable **si** une comparaison équitable sur vérité terrain humaine le justifie. Cette décision est tracée et documentée (`docs/B_classification_ml`, fiche modèle).

> **Critères couverts (C3.3.3).** **La problématique nécessitant un arbitrage est exposée avec ses conséquences** (promouvoir ou non le transformer). **Les options possibles sont détaillées** (promouvoir / garder / hybride, avec avantages-inconvénients). **La décision d'arbitrage est argumentée et résout la problématique** (garder le LinearSVC : accuracy, coût de déploiement, absence de validation humaine équitable).

---

## 5. C3.4 — Veiller et agir de façon responsable

### C3.4.1 — Méthodologie de veille

**Livrable : une méthodologie de veille.**

#### Choix de la méthodologie de recueil

Ma veille combine trois canaux, choisis pour leur **rapport signal/effort** :
- **Veille technique ML** : suivi de la littérature et des bibliothèques (calibration de modèles, *focal loss*, transformers multilingues type XLM-R) via publications et documentation open-source.
- **Veille réglementaire / tarifaire** : consommation de **sources externes rejouables** — l'API publique Azure Retail Prices pour les coûts de stockage réels, plutôt que des hypothèses.
- **Veille outillée** : automatisation partielle (le module de collecte tarifaire rafraîchit les coûts à la demande), qui transforme une veille manuelle en flux reproductible.

**Bénéfice attendu** : des décisions techniques et économiques ancrées dans des sources réelles et actualisables, pas dans des constantes figées.

#### Résultat d'une action de veille et impact métier

**Action concrète** : la veille sur la **calibration des modèles** a conduit à mesurer l'ECE et à adopter une confiance graduée plutôt qu'un forfait. **Impact sur les pratiques métier** : les scores de confiance affichés au décideur sont désormais **fiables** — un « 90 % » signifie vraiment ~90 %, ce qui change la façon dont l'analyste priorise ses vérifications. Seconde action : la veille tarifaire a **remplacé des coûts inventés** (0,276 $/Go/an) par des tarifs sourcés (API Azure, 0,2120 $/Go/an), fiabilisant tout le calcul de ROI.

> **Critères couverts (C3.4.1).** **Le choix de la méthodologie de recueil est argumenté** avec ses bénéfices (veille technique + réglementaire/tarifaire + outillée, ancrage dans des sources réelles). **Le résultat d'une action de veille est présenté** (adoption de la calibration ; sourcing des coûts) et **identifie l'impact sur les pratiques métier** (confiance fiable pour la priorisation, ROI crédible).

---

### C3.4.2 — Plan d'actions RSE, sécurité, éthique et confidentialité

**Livrable : un plan d'actions relatif aux enjeux RSE, de sécurité, d'éthique et de confidentialité.**

#### Les enjeux de la science des données pour ce projet

- **Environnement (RSE)** : le stockage de données inactives consomme de l'énergie. L'archivage « froid » réduit cette empreinte — le rapport de coût chaud/archive ×9,8 reflète un différentiel énergétique réel. Le projet a donc un **impact environnemental positif par nature**.
- **Confidentialité** : les métadonnées peuvent contenir des PII (RGPD).
- **Éthique de l'IA** : un modèle qui surévalue sa propre performance induit le décideur en erreur.
- **Sécurité** : l'accès à une base de production est un risque.

#### Arbitrages de priorisation

Face à des ressources limitées (projet solo), j'ai **priorisé la confidentialité et l'éthique** — enjeux à risque légal et de confiance immédiat — avant l'optimisation fine de l'empreinte carbone, bénéfice déjà acquis par nature. Ce choix est assumé : mieux vaut une PII bien protégée qu'un gain CO₂ marginal sur-optimisé.

#### Le plan d'actions

| Sujet | Action mise en œuvre | Délai |
|---|---|---|
| **Confidentialité (RGPD)** | Masquage PII dans les exports + chiffrement `pgcrypto` au repos + minimisation (métadonnées seules) | **Réalisé** (P2, P4) |
| **Sécurité** | Accès Oracle en lecture seule ; comptes PostgreSQL à moindre privilège (`pfe_reader`/`pfe_writer`) | **Réalisé** (P4) |
| **Éthique IA** | Publication de la **justesse réelle** (~58-75 %, pas le 89 % du holdout LLM) ; garde-fou `review_required` ; refus de promouvoir un modèle sur un holdout gonflé | **Réalisé** (P0-P3) |
| **Environnement (RSE)** | Recommandations d'archivage réduisant le stockage chaud ; coûts/gains sourcés | **Réalisé** (P1, P4) |
| **Confidentialité — suite** | Externaliser secrets et clés vers un coffre (HashiCorp/Azure Key Vault) | Court terme (industrialisation) |
| **RSE — suite** | Quantifier l'empreinte CO₂ évitée (kWh/To archivé) | Moyen terme |

> **Critères couverts (C3.4.2).** **Les enjeux RSE de la science des données sont détaillés** (empreinte du stockage, confidentialité, éthique IA, sécurité). **Les arbitrages de priorisation sont précisés et justifiés** (confidentialité/éthique avant optimisation CO₂ fine). **Le plan d'actions précise, pour chaque sujet, l'action mise en œuvre et les délais** (RGPD/pgcrypto, moindre privilège, éthique IA honnête, archivage — réalisés ; coffre à secrets et quantification CO₂ — à venir).

---

## 6. Conclusion

Ce bloc démontre la **conduite de bout en bout** d'un projet data :

- **Cadrer et dimensionner** : problématique, objectifs, cadre RGPD, contraintes et RSE clairement posés ; dimensionnement honnête (solo réalisé, équipe cible pour l'industrialisation) et faisabilité prouvée.
- **Planifier et suivre** : méthodologie **Kanban** justifiée, planning **réel issu de l'historique Git** (6 phases), matrice RACI pour le déploiement, et un suivi outillé (Git + `pipeline_run` + dashboard) avec indicateurs argumentés.
- **Constituer et piloter l'équipe** : plan de compétences, outils managériaux et un **cas d'arbitrage réel** (production LinearSVC vs XLM-R) tranché et documenté.
- **Veiller et agir responsable** : veille technique et tarifaire outillée, et un plan d'actions RSE/sécurité/éthique **majoritairement déjà réalisé** (RGPD, moindre privilège, IA honnête, archivage vertueux).

La conduite du projet reflète le même principe que sa technique : **l'honnêteté** — sur le périmètre (solo assumé), sur la performance (justesse réelle publiée) et sur les décisions (arbitrages tracés).

---

## Annexes (hors décompte de pages)

- **A. Planning détaillé** : phases P0→P5 avec commits Git de référence.
- **B. Matrice RACI** : équipe cible de déploiement.
- **C. Grille de compétences** : actuelles vs à acquérir, plan de formation.
- **D. Cas d'arbitrage** : fiche de décision LinearSVC vs XLM-R (chiffres comparés).
- **E. Plan d'actions RSE** : sujets, actions, délais, statut.
