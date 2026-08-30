# BLOC 3 — Élaborer et piloter un projet data

**Titre visé :** Ingénieur en science des données spécialisé en infrastructure data ou en apprentissage automatique — RNCP 39586 (niveau 7)
**Candidat :** HAOUARI Salem · **Date :** 17/08/2026
**Projet :** Solution de gouvernance et d'archivage intelligent des données d'un ERP PeopleSoft (Oracle EP92U038)
**Dépôt de code :** https://github.com/Salem2025s/data-archiving-solution

## Pages liminaires — note de lecture pour le jury

*Cette note, le sommaire et la table de traçabilité constituent, avec la page de garde, les pages liminaires du dossier. Le corps soumis au plafond de 20 pages commence au § 1.*

Chaque section correspond à une compétence du bloc, de C3.1.1 à C3.4.2. Elle présente d'abord le livrable attendu par la grille, puis se termine par un encadré « Critères couverts » qui reprend les exigences point par point.

**Périmètre du bloc.** Ce dossier traite de la conduite du projet, pas de sa technique : celle-ci est couverte par les Blocs 1, 2 et 5. Les éléments de contenu technique n'apparaissent ici que lorsqu'ils fondent une décision de pilotage.

**Conditions de réalisation, énoncées d'emblée.** Le projet a été conduit **par une seule personne**, à disponibilité partielle, avec des points d'avancement périodiques auprès du tuteur et de l'équipe. Cette configuration a deux conséquences sur la lecture du dossier. D'une part, le pilotage réellement exercé est un **pilotage de parties prenantes** et non l'encadrement d'une équipe hiérarchique : c'est ce qui est documenté au § 4.2. D'autre part, les livrables de dimensionnement d'équipe et de développement des compétences sont construits pour le **scénario d'industrialisation chez un client**, explicitement identifié comme tel à chaque fois. Aucune équipe qui n'a pas existé n'est présentée au passé.

**Traçabilité des chiffres.** Le planning et le suivi s'appuient sur des traces vérifiables : la table `admin.pipeline_run` de l'entrepôt, qui horodate chaque exécution du pipeline, et l'historique Git du dépôt. Les valeurs qui relèvent de l'estimation ou de l'hypothèse — charge reconstituée, taux journalier, volumétrie d'un client type — sont signalées comme telles à l'endroit où elles servent.

## Sommaire

| § | Section | Compétence |
|---|---|---|
| 1 | Contexte et présentation du projet | — |
| 2 | **C3.1 — Cadrer et dimensionner** | |
| 2.1 | Cadrage du projet | C3.1.1 |
| 2.2 | Dimensionnement du projet | C3.1.2 |
| 2.3 | Documentation projet | C3.1.3 |
| 3 | **C3.2 — Planifier et suivre** | |
| 3.1 | Planning et méthodologie | C3.2.1 |
| 3.2 | Suivi de l'avancement | C3.2.2 |
| 4 | **C3.3 — Constituer et piloter l'équipe** | |
| 4.1 | Plan de développement des compétences | C3.3.1 |
| 4.2 | Outils de communication et managériaux | C3.3.2 |
| 4.3 | Cas d'arbitrage rencontrés | C3.3.3 |
| 5 | **C3.4 — Veiller et agir de façon responsable** | |
| 5.1 | Méthodologie de veille | C3.4.1 |
| 5.2 | Plan d'actions RSE, sécurité, éthique et confidentialité | C3.4.2 |
| 6 | Conclusion | — |
| — | Annexes A à I (hors décompte de pages) | — |

### Table de traçabilité — grille d'évaluation → dossier

Chaque livrable attendu par la grille est traité dans une section dédiée : **C3.1.1** le cadrage au § 2.1 ; **C3.1.2** le dimensionnement au § 2.2, chiffrage compris ; **C3.1.3** la documentation projet au § 2.3 ; **C3.2.1** le planning au § 3.1 ; **C3.2.2** l'outil de suivi et le tableau de bord au § 3.2 ; **C3.3.1** le plan de développement des compétences au § 4.1 ; **C3.3.2** les outils de communication et managériaux au § 4.2 ; **C3.3.3** les cas d'arbitrage au § 4.3 ; **C3.4.1** la méthodologie de veille au § 5.1 ; **C3.4.2** le plan d'actions RSE au § 5.2. La correspondance critère par critère figure en annexe I.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

## 1. Contexte et présentation du projet

Le projet vise à doter une organisation exploitant un ERP Oracle PeopleSoft, instance `EP92U038`, d'une solution capable de cartographier son patrimoine de données, d'en chiffrer le coût de stockage et de recommander une stratégie d'archivage. Il a été conçu comme un produit substituable d'un client à l'autre : la source n'est qu'un paramètre de configuration, et l'instance de référence sert de terrain de validation. Le commanditaire est la Direction des Systèmes d'Information, dont le besoin, recueilli en entretien de cadrage, tient en une phrase : la base de l'ERP grossit sans que personne sache ce qu'elle contient, ce qu'elle coûte, ni ce qui peut en être archivé sans risque.

La solution livrée comporte un pipeline d'extraction et de transformation, un entrepôt PostgreSQL en architecture médaillon, un classifieur de domaines métier, un moteur de scoring d'archivabilité et un dashboard décisionnel. Au terme du dernier run, elle a classé **167 260 actifs** en sept domaines métier, chiffré leur coût de stockage sur des tarifs sourcés et produit des recommandations d'archivage priorisées. Ce bloc ne revient pas sur ces réalisations : il documente la manière dont le projet a été cadré, dimensionné, planifié, suivi et arbitré, et la façon dont les enjeux de veille et de responsabilité y ont été traités.

## 2. C3.1 — Cadrer et dimensionner

### 2.1 — C3.1.1 : Cadrage du projet

**Livrable : le cadrage du projet.**

#### 2.1.1 Problématique

Les décisions d'archivage se prennent au cas par cas, sans vision d'ensemble ni chiffrage, et reposent sur la connaissance de quelques personnes. Formulée en termes de projet, la question devient : **comment produire, de façon automatique et rejouable, une cartographie fiable d'un patrimoine ERP, en mesurer le coût par objet métier et recommander une stratégie d'archivage justifiée, sans jamais mettre en péril l'intégrité du système ni la conformité réglementaire ?**

#### 2.1.2 Objectifs et livrables

| Objectif | Livrable produit | Bloc |
|---|---|---|
| Collecter et structurer les métadonnées de l'ERP | Pipeline ETL et entrepôt PostgreSQL en architecture médaillon | Bloc 1 |
| Classer automatiquement les tables par domaine métier | Classifieur de production et scoring persistés en base | Blocs 2 et 5 |
| Chiffrer les coûts et le ROI, recommander l'archivage | Dashboard décisionnel et export tableur | Bloc 2 |
| Sécuriser la chaîne de bout en bout | Chiffrement des données personnelles, moindre privilège, accès source en lecture seule | Bloc 1 |
| Rendre les utilisateurs autonomes | Support de formation et documentation technique | Bloc 2 |

#### 2.1.3 Cadre réglementaire

Le projet manipule des métadonnées susceptibles de contenir des données personnelles : identifiants d'opérateurs, adresses électroniques présentes dans les journaux. Il relève donc du **RGPD**, ce qui impose trois obligations traitées dès la conception. La **minimisation** d'abord : seules les métadonnées sont collectées, jamais le contenu métier des tables. La **protection** ensuite : masquage des données personnelles dans les exports et chiffrement au repos dans la base. La **traçabilité** enfin : chaque exécution est journalisée et rejouable.

S'y ajoute une obligation propre au métier de l'archivage, relevée en entretien avec le référent Finance : les **durées légales de conservation** interdisent de traiter toutes les données de la même manière. Archiver n'est pas supprimer, et la distinction devait apparaître explicitement dans les recommandations produites.

#### 2.1.4 Contraintes

| Type | Contrainte | Origine |
|---|---|---|
| **Technique** | Source accessible par VPN uniquement ; aucune écriture sur l'ERP ; noms de tables opaques ; volume élevé (plus de 160 000 actifs) | Entretien DBA |
| **Réglementaire** | RGPD sur les métadonnées ; durées légales de conservation à respecter | Entretien référent métier |
| **Données** | Absence de vérité terrain : aucune cartographie préexistante ne permet de valider les classifications | Constat de cadrage |
| **Ressources** | Une seule personne, à disponibilité partielle ; pas de budget d'infrastructure ; outils open source imposés | Contexte du projet |
| **Délai** | Échéances de certification fixes, non négociables (§ 3.1.2) | Modalités d'évaluation |
| **Produit** | Solution générique, base substituable, déployable chez d'autres clients PeopleSoft | Commanditaire |

#### 2.1.5 Points de vigilance et registre des risques

Les contraintes ci-dessus se traduisent en risques, suivis pendant toute la durée du projet.

| Risque | Probabilité | Impact | Mesure de maîtrise | Statut |
|---|---|---|---|---|
| **Recommander l'archivage d'une donnée mal classée** | Moyenne | **Critique** | Marqueur `review_required`, confiance affichée sur chaque classification, aucune action automatique sur les données | Maîtrisé |
| Indisponibilité du VPN bloquant l'extraction | Moyenne | Élevé | Extraction incrémentale par préfixe, reprise sur incident, journalisation des runs | Maîtrisé |
| Absence de vérité terrain préexistante | **Élevée** | Élevé | Labels générés par LLM local, échantillon validé par un expert ; boucle d'apprentissage actif ; métriques sur holdout indépendant | Maîtrisé, limite résiduelle documentée |
| Compétence rare portée par une seule personne (transformers) | Élevée | Moyen | Modèle de production volontairement simple et interprétable ; le modèle profond reste un axe de recherche | Maîtrisé par la décision du § 4.3.1 |
| Dérive du périmètre vers la technique au détriment du pilotage | Moyenne | Moyen | Découpage en phases jalonnées par les échéances de certification | Maîtrisé |
| Écriture accidentelle sur l'ERP de production | Faible | **Critique** | Compte Oracle en lecture seule, vérifié par la pratique | Éliminé |

Le premier risque est le seul qui soit à la fois critique et non éliminable : une classification automatique se trompe, par construction, dans une proportion mesurable des cas. C'est lui qui a dicté le principe central du produit — **la solution recommande, elle n'exécute jamais** — et qui structure le cas d'arbitrage du § 4.3.1.

#### 2.1.6 Enjeux RSE

Le projet porte un bénéfice environnemental intrinsèque : déplacer des données inactives d'un stockage actif vers un palier d'archive réduit la consommation énergétique associée, les paliers froids reposant sur des supports moins sollicités et moins répliqués à chaud. Le rapport de coût de 9,8 entre les deux paliers en donne un ordre de grandeur, sans que la proportionnalité entre prix et consommation soit établie : la quantification de l'empreinte réellement évitée reste une action à mener (§ 5.2.3).

Deux autres dimensions relèvent de la responsabilité et sont traitées au § 5.2 : l'**éthique de l'IA**, avec la publication de la performance réelle du modèle plutôt que d'une métrique flatteuse, et la **sobriété du modèle retenu**, un classifieur léger de quelques mégaoctets ayant été préféré à un transformeur de 2,1 Go dont l'entraînement et l'inférence sont bien plus coûteux.

> **Critères couverts (C3.1.1).** Le cadrage identifie ✓ la problématique (§ 2.1.1), ✓ les objectifs et les livrables du projet (§ 2.1.2), ✓ le cadre réglementaire, RGPD et durées légales de conservation (§ 2.1.3), ✓ les contraintes, chacune rattachée à son origine, et les points de vigilance, formalisés en registre des risques avec probabilité, impact, mesure de maîtrise et statut (§ 2.1.4 et § 2.1.5), ✓ les enjeux RSE (§ 2.1.6). Le contexte et les enjeux sont posés au § 1, et le dimensionnement en délai et budget qui en découle au § 2.2.

### 2.2 — C3.1.2 : Dimensionnement du projet

**Livrable : le dimensionnement du projet.**

Deux configurations sont dimensionnées séparément : le **projet réalisé**, un prototype conduit par une personne, et le **scénario d'industrialisation** chez un client, qui suppose une équipe. Les confondre reviendrait à présenter comme acquis un dimensionnement qui reste une projection.

#### 2.2.1 Ressources humaines

| | Projet réalisé | Scénario d'industrialisation |
|---|---|---|
| **Effectif** | Une personne, plusieurs rôles : ingénierie de données, apprentissage automatique, analyse métier, sécurité | Équipe de 3 à 4 : chef de projet data, ingénieur données, ingénieur ML, analyste métier |
| **Parties prenantes** | Tuteur, référents métier et DBA, sollicités lors de points d'avancement périodiques | Commanditaire DSI, référents métier, exploitation, délégué à la protection des données |
| **Disponibilité** | Partielle et discontinue, en fonction des créneaux disponibles | Temps plein sur la durée du lot |

La répartition des responsabilités du scénario d'industrialisation est formalisée en matrice RACI (§ 3.1.4 et annexe B).

#### 2.2.2 Ressources matérielles et logistiques

Un poste de développement unique sous Python 3.13 et Docker Desktop. L'entrepôt tourne dans un conteneur PostgreSQL 16 local. L'accès à la source Oracle se fait par VPN, l'instance étant fournie. L'ensemble de l'outillage est open source — Python, PostgreSQL, Prefect, Streamlit, scikit-learn — ce qui ramène le coût de licence à zéro. Seul l'entraînement du modèle profond a nécessité un GPU, de façon ponctuelle et mutualisable.

#### 2.2.3 Chiffrage : charge, coût et délai

**Charge du projet réalisé.** La charge ci-dessous est **reconstituée a posteriori** à partir des dates de phase, des runs journalisés dans `admin.pipeline_run` et de la densité de l'historique Git. Il ne s'agit pas d'un relevé de temps.

| Phase | Période | Charge estimée | Part |
|---|---|---:|---:|
| P0 — Cadrage et collecte | 09/03 → 31/03 | 9 j·h | 15 % |
| P1 — Modélisation et analyse | 01/04 → 31/05 | 22 j·h | 37 % |
| P2 — Sûreté et fiabilité | 01/06 → 09/06 | 5 j·h | 8 % |
| P3 — Apprentissage profond | 09/06 → 19/06 | 6 j·h | 10 % |
| P4 — Sécurité et sources externes | 07/07 → 17/07 | 6 j·h | 10 % |
| P5 — Certification | 14/07 → 29/08 | 12 j·h | 20 % |
| **Total** | **09/03 → 29/08** | **60 j·h** | **100 %** |

La période compte 173 jours calendaires, soit environ 124 jours ouvrés hors congés : la charge correspond donc à un taux d'occupation de l'ordre de **48 %**, cohérent avec une disponibilité partielle et discontinue. La coupure de dix-sept jours entre P3 et P4, du 20 juin au 6 juillet, correspond à une interruption sans activité sur le projet ; elle est incluse dans la période de référence, ce qui minore le taux affiché.

Le coût d'infrastructure engagé est **nul** : outillage open source, exécution locale et instance source fournie. Le GPU utilisé pour l'entraînement du modèle profond a été mobilisé ponctuellement sur une ressource existante, sans coût marginal pour le projet.

**Budget du scénario d'industrialisation.** Le chiffrage ci-dessous vaut pour un déploiement de la solution chez un client, sur son instance PeopleSoft.

| Poste | Charge | Coût |
|---|---:|---:|
| Cadrage et spécifications | 15 j·h | 7 500 € |
| Collecte et ETL sur l'instance client | 40 j·h | 20 000 € |
| Modélisation et scoring | 30 j·h | 15 000 € |
| Dashboard et restitution | 25 j·h | 12 500 € |
| Sécurité et conformité RGPD | 20 j·h | 10 000 € |
| Recette et documentation | 20 j·h | 10 000 € |
| **Sous-total charge** | **150 j·h** | **75 000 €** |
| Infrastructure : base managée et hébergement, 5 mois | — | 1 000 € |
| Provision pour aléas, 10 % de la charge et de l'infrastructure | — | 7 600 € |
| **Budget indicatif** | | **≈ 84 000 € HT** |

*Hypothèse de valorisation : taux journalier moyen de 500 € HT, ordre de grandeur du marché français pour des profils data confirmés en prestation. Ce taux est une hypothèse de chiffrage, non un tarif négocié. Le détail par lot et par rôle porteur figure en annexe C.*

**Délai.** 150 jours-homme répartis sur une équipe de 3 à 4 personnes représentent environ deux mois de travail effectif, mais les dépendances entre lots — la collecte conditionne la modélisation, qui conditionne la restitution — et le temps de recette portent le délai calendaire à **quatre à cinq mois**.

#### 2.2.4 Analyse de faisabilité

**Faisabilité technique : démontrée.** Le prototype fonctionne de bout en bout sur des données réelles, avec 167 260 actifs classés, des coûts et un ROI calculés, et une chaîne sécurisée en exploitation. Les risques identifiés au § 2.1.5 sont assortis de mesures effectives.

**Faisabilité organisationnelle : conditionnée.** Le déploiement suppose un accès en lecture à l'instance client et un référent métier disponible pour la validation des classifications. Ces deux prérequis figurent au registre des risques du déploiement.

**Faisabilité économique : le point à ne pas éluder.** Un budget de 84 000 € ne se justifie pas par la seule économie de stockage. Au taux mesuré de 195 $ par téraoctet archivé et par an, une base ERP de quelques téraoctets ne dégage que quelques centaines de dollars d'économie annuelle : le retour sur investissement par ce seul canal serait hors de portée, et il faut le dire avant qu'un jury ou un client ne le calcule.

La justification repose sur un autre poste : le **coût évité de la cartographie manuelle**. Cartographier 167 260 actifs à la main, à trente secondes par actif pour un expert du progiciel, représente environ 1 400 heures, soit de l'ordre de 175 jours-homme sur une base de 8 heures, et plus de 85 000 € au même taux journalier — pour un seul patrimoine, et pour un résultat figé le jour de sa production alors que la solution se rejoue à chaque exécution. S'y ajoutent la réduction de la dépendance à quelques experts et la capacité à répondre à une demande de conformité. L'économie de stockage reste un bénéfice réel, significatif à grande échelle, mais elle complète le dossier économique au lieu de le fonder.

> **Critères couverts (C3.1.2).** Le dimensionnement comporte ✓ les ressources humaines, pour le projet réalisé comme pour l'équipe cible, parties prenantes comprises (§ 2.2.1), ✓ les ressources matérielles et logistiques (§ 2.2.2), ✓ un chiffrage en coût et en délai — 60 jours-homme sur 173 jours calendaires pour le prototype, 150 jours-homme et 84 000 € HT sur quatre à cinq mois pour l'industrialisation, hypothèse de taux journalier explicitée (§ 2.2.3, annexe C) — et ✓ une analyse de faisabilité technique, organisationnelle et économique, cette dernière établissant que le dossier repose sur le coût évité de la cartographie manuelle (§ 2.2.4).

### 2.3 — C3.1.3 : Documentation projet

**Livrable : la documentation projet.**

#### 2.3.1 Parties prenantes et registre associé

La documentation ne peut être « rédigée dans un vocabulaire compréhensible par les parties prenantes » qu'à condition d'avoir identifié ces parties prenantes et ce que chacune attend.

| Partie prenante | Attente vis-à-vis du projet | Document qui la sert |
|---|---|---|
| Commanditaire DSI | Un chiffrage et une vision présentable en comité | Dashboard, dossiers de synthèse |
| Référent métier | Savoir quand se fier à une classification | Support de formation, dictionnaire des indicateurs |
| DBA et exploitation | Garantie qu'aucune écriture n'atteint l'ERP | Documentation technique, journal des runs |
| Développeur reprenant la solution | Comprendre, modifier, réexécuter | Documentation technique, procédure de reproduction |
| Jury de certification | Vérifier qu'un chiffre est traçable | Dossiers par bloc, fiche de modèle |

#### 2.3.2 Une documentation à deux registres

Chaque grande fonction du projet est documentée en deux versions : une **version métier**, au vocabulaire accessible aux décideurs et aux référents, et une **version technique**, qui descend au détail d'implémentation. C'est ce dédoublement qui permet de satisfaire des attentes aussi éloignées que celles d'un comité de direction et d'un développeur.

| Document | Public | Rôle |
|---|---|---|
| `README.md`, `docs/INDEX.md` | Tous | Point d'entrée, installation, lecture critique |
| `docs/A_…` à `docs/E4_…`, en version métier et technique | Métier et développement | Spécifications fonctionnelles et techniques par fonction |
| `docs/certification/BLOC1/2/3` | Jury et management | Dossiers de synthèse par bloc |
| `artifacts/production_model_card.md` | Data scientists | Fiche de modèle, source de vérité sur le modèle déployé |
| `docs/PRODUCTION_READINESS.md` | Management | Évaluation de maturité, sous forme de feux |

Cette structure tient lieu de **cahier des charges vivant** : les spécifications fonctionnelles, ce que le système doit faire, et techniques, comment il le fait, sont versionnées avec le code et évoluent avec lui. Une spécification figée dans un document séparé aurait divergé du produit dès la première réorientation.

Le **sommaire des spécifications** figure en annexe D : six exigences fonctionnelles et six exigences techniques, chacune assortie de son critère d'acceptation et du document qui la porte. C'est ce qui permet de vérifier qu'une exigence a bien été satisfaite, et non seulement énoncée.

> **Critères couverts (C3.1.3).** ✓ Les parties prenantes concernées sont identifiées, avec pour chacune son attente et le document qui y répond (§ 2.3.1). ✓ La documentation projet est en adéquation avec le cadrage et présente l'ensemble des caractéristiques du projet : le **sommaire des spécifications de l'annexe D** énumère six exigences fonctionnelles et six exigences techniques avec leur critère d'acceptation, complétées de la fiche de modèle, de l'évaluation de maturité et des dossiers de synthèse (§ 2.3.2). ✓ Elle est rédigée dans un vocabulaire compréhensible par les parties prenantes, grâce au dédoublement systématique en registre métier et registre technique.

## 3. C3.2 — Planifier et suivre

### 3.1 — C3.2.1 : Planning et méthodologie

**Livrable : le planning projet.**

#### 3.1.1 Choix de la méthodologie : Kanban

Le projet a été conduit en **Kanban**, en flux continu, et non en Scrum.

Un projet exploratoire de science des données voit ses priorités évoluer au fil des découvertes. Le cas s'est présenté : le score d'archivabilité s'est révélé quasi constant sur le périmètre disponible, ce qui a imposé de réorienter une partie du travail d'analyse. Le flux continu du Kanban — *à faire*, *en cours*, *fait*, avec limitation du travail en cours — absorbe ce type de réorientation mieux que des sprints à périmètre figé. À cela s'ajoute une raison de proportionnalité : les rituels de Scrum, mêlée quotidienne, revue et rétrospective, sont dimensionnés pour une équipe et deviennent une charge sans contrepartie pour une personne seule.

**Bénéfices attendus et obtenus :** visualisation permanente de l'avancement, souplesse de repriorisation sans rompre un engagement de sprint, et limitation du travail en cours simultané, qui a évité l'éparpillement entre chantiers techniques.

L'outil de planification est un **tableau Kanban jalonné par les échéances de certification**, cohérent avec la méthodologie puisqu'il associe un flux continu à des jalons externes fixes. Le tableau comporte quatre colonnes — *à faire*, *en cours*, *en revue*, *fait* — avec une limite de deux cartes simultanées en colonne *en cours*, seuil au-delà duquel l'éparpillement entre chantiers techniques devenait sensible. Chaque carte correspond à un lot de travail du § 3.1.3 et se solde par un commit. Le planning qui en résulte est matérialisé sous forme de diagramme de Gantt (annexe A).

#### 3.1.2 Jalons externes imposés

Le projet est contraint par quatre échéances non négociables, fixées par les modalités d'évaluation. Elles constituent l'ossature du planning.

| Jalon | Échéance | Statut |
|---|---|---|
| Dépôt du Bloc 1, rendu écrit | Semaine 29 — 13 au 17/07/2026 | Tenu |
| Dépôt du Bloc 2, rendu écrit | Semaine 31 — 27 au 31/07/2026 | Tenu |
| Dépôt du Bloc 3, rendu écrit | Semaine 34 — 17 au 21/08/2026 | En cours |
| Soutenance orale du bloc de spécialité | Semaines 36 à 40 — 01 au 29/09/2026 | À venir |

#### 3.1.3 Découpage en phases et en lots

Le projet a débuté le 9 mars 2026. Le planning ci-dessous est daté par des traces : les premières phases par les runs journalisés dans `admin.pipeline_run`, les suivantes par l'historique Git, le dépôt ayant été formalisé en juin.

| Phase | Période | Lots de travail | Jalon de vérification |
|---|---|---|---|
| **P0** — Cadrage et collecte | 09/03 → 31/03 | Cadrage · connexion Oracle · extraction du dictionnaire · chargement | Runs 3 et 4 |
| **P1** — Modélisation et analyse | 01/04 → 31/05 | Modèle en étoile · classification · comparaison inter-runs · ROI | Runs 5 et 6 |
| **P2** — Sûreté et fiabilité | 01/06 → 09/06 | Reprise sur incident · audit · masquage · calibration | Commits `phase0`, `phase1` |
| **P3** — Apprentissage profond | 09/06 → 19/06 | Fine-tuning du transformeur · page de test | Commits `xlmr` |
| **P4** — Sécurité et sources externes | 07/07 → 17/07 | Tarifs API · `pgcrypto` · rôles séparés · dashboard | Commits `extract`, `security` |
| **P5** — Certification | 14/07 → 29/08 | Dossiers des quatre blocs · annexes · soutenance | Dépôts S29, S31, S34 |

![Diagramme de Gantt du projet : six phases réelles de mars à août 2026, datées par les runs du pipeline et l'historique Git.](img/bloc3_gantt.png)

#### 3.1.4 Répartition des activités : matrice RACI

Le projet réalisé n'a pas comporté de répartition entre plusieurs personnes. La matrice ci-dessous vaut donc pour le **scénario d'industrialisation**, où elle affecte chaque activité selon les compétences des rôles. R désigne celui qui réalise, A celui qui approuve, C celui qui est consulté, I celui qui est informé.

| Activité | Chef de projet | Ingénieur données | Ingénieur ML | Analyste métier |
|---|---|---|---|---|
| Cadrage et spécifications | A | C | C | **R** |
| Collecte et ETL | I | **R** | C | I |
| Modélisation et scoring | A | C | **R** | C |
| Dashboard et restitution | I | C | I | **R** |
| Sécurité et conformité | A | **R** | I | C |
| Recette et validation métier | A | I | I | **R** |

Chaque membre porte un domaine principal tout en étant consulté sur les interfaces, ce qui évite à la fois la surcharge d'une personne et le cloisonnement des compétences.

#### 3.1.5 Chemin critique et points de vigilance

Le **chemin critique** relie l'accès à la source, l'extraction, la construction du modèle en étoile, la classification et enfin la restitution. Toute rupture en amont gèle l'ensemble de la chaîne : sans extraction, il n'y a ni classification ni chiffrage. La conséquence pratique est que la **disponibilité du VPN conditionne tout le projet**, ce qui a justifié d'investir tôt dans la résilience de la collecte — extraction incrémentale, reprise sur incident, journalisation.

Deux autres points de vigilance ont été suivis. La **compétence rare** que constitue le fine-tuning de transformeurs représente une fragilité dès lors qu'elle est portée par une seule personne ; elle a été traitée par une décision d'architecture, en gardant en production un modèle simple et interprétable (§ 4.3.1). Et le **jalonnement serré de la phase P5**, où trois dépôts se succèdent en cinq semaines, imposait de commencer la rédaction avant la fin des développements, ce qui explique le chevauchement de P4 et P5 dans le diagramme.

#### 3.1.6 Prise en compte des personnes en situation de handicap

L'accessibilité a été traitée à deux niveaux. Sur le **livrable**, le dashboard applique des règles d'accessibilité visuelle : la couleur n'est jamais le seul vecteur d'information, les échelles d'intensité sont monochromes pour ne pas pénaliser les déficiences de la vision des couleurs, et le contraste respecte le seuil de niveau AA. Deux limites subsistent, la navigation clavier complète et les libellés alternatifs sur les graphiques, identifiées comme travaux à mener.

Sur l'**organisation du travail**, le scénario d'industrialisation prévoit des créneaux de réunion adaptés, une documentation écrite systématique qui permet le travail asynchrone plutôt que la seule transmission orale, et un poste de travail adapté. Ces mesures profitent d'ailleurs à toute l'équipe, en particulier lorsqu'elle est distribuée.

> **Critères couverts (C3.2.1).** ✓ Le choix du Kanban est justifié avec ses bénéfices, par comparaison argumentée avec Scrum (§ 3.1.1). ✓ L'outil de planification, tableau Kanban à quatre colonnes et limite de travail en cours, complété du diagramme de Gantt, est compatible avec cette méthodologie qui associe flux continu et jalons externes. ✓ Le planning est découpé en six phases et en lots (§ 3.1.3) et ✓ permet de visualiser les phases, de la collecte à la restitution, sur le Gantt. ✓ Les tâches sont assignées selon les compétences par une matrice RACI (§ 3.1.4), ✓ qui tient compte des personnes en situation de handicap, sur le livrable comme sur l'organisation du travail (§ 3.1.6). ✓ Les points de vigilance sont soulignés — chemin critique, compétence rare, jalonnement serré (§ 3.1.5) — et formalisés en registre des risques (§ 2.1.5).

### 3.2 — C3.2.2 : Suivi de l'avancement

**Livrable : un outil de suivi de projet et un tableau de bord.**

#### 3.2.1 Les trois outils de suivi

Le dispositif de suivi repose sur trois outils complémentaires, cohérents avec le pilotage en flux du Kanban.

Le **tableau Kanban** porte le flux courant, décrit au § 3.1.1. Trois outils l'alimentent et le tracent.

**Git** tient le journal exhaustif de l'avancement. Les commits, datés et structurés par préfixe (`feat`, `fix`, `docs`), matérialisent le flux : chaque commit correspond à une carte terminée. C'est la source qui permet de reconstituer la charge par phase.

**La table `admin.pipeline_run`** trace chaque exécution du pipeline : identifiant de run, flux exécuté, statut en succès ou en échec, horodatages de début et de fin. Elle donne le suivi opérationnel et sert de preuve de datation pour les premières phases.

**Le dashboard Streamlit** constitue le tableau de bord vivant : il présente les indicateurs métier et l'historique des runs, et sert de support aux points d'avancement.

#### 3.2.2 Indicateurs de suivi

Le choix des indicateurs suit une règle simple : couvrir les trois dimensions attendues d'un pilotage — l'avancement, le respect des délais, la maîtrise des coûts — et compléter les mesures quantitatives par des indicateurs qualitatifs, faute de quoi le pilotage se ferait sur les seuls chiffres faciles à produire.

| Indicateur | Type | Dimension | Ce qu'il pilote |
|---|---|---|---|
| Commits par phase | Quantitatif | Avancement | Progression du développement |
| Couverture de classification | Quantitatif | Avancement | Complétude de l'analyse |
| Statut des runs, succès ou échec | Quantitatif | Avancement | Santé opérationnelle du pipeline |
| **Jalons tenus sur jalons prévus** | Quantitatif | **Délai** | Respect des échéances de certification |
| **Durée réelle d'une phase rapportée à sa durée cible** | Quantitatif | **Délai** | Dérive du planning, phase par phase |
| **Coût engagé, infrastructure et licences** | Quantitatif | **Coût** | Maîtrise du budget : nul sur toute la durée du prototype |
| Taux de revue `review_required` | Quantitatif | Qualité | Fiabilité des résultats produits |
| Justesse et calibration du modèle | Quantitatif | Qualité | Performance réelle, non l'accord avec l'annotateur |
| **Appréciation de fin de phase** : la phase répond-elle à son objectif ? | **Qualitatif** | Qualité | Décision de clore ou de prolonger un lot |
| **Retour des parties prenantes** en point d'avancement | **Qualitatif** | Pilotage | Alerte précoce sur un désalignement métier |

**Valeurs relevées à la date de rédaction.**

| Indicateur | Valeur |
|---|---|
| Jalons de dépôt échus, tenus | 2 sur 2 ; le troisième en cours |
| Phases closes | 5 sur 6 ; P5 en cours |
| Dérive de planning la plus marquée | P1, deux mois contre une cible d'un mois |
| Actifs classés, couverture | 167 260, soit la totalité du catalogue |
| Taux de revue | 27,1 % des actifs |
| Performance du modèle de production | Holdout : macro-F1 0,885 · accuracy 0,922 · AUC 0,991 |
| Coût engagé | 0 € sur toute la durée du prototype |

La dérive de P1 est le seul écart de planning significatif. Elle tient à la réorientation du score d'archivabilité, et c'est elle qui a déclenché l'arbitrage du § 4.3.2.

Le mélange des types n'est pas décoratif. Le taux de revue, indicateur qualitatif, alerte sur un risque que la seule justesse masquerait : un modèle peut être juste en moyenne tout en étant incertain sur les cas qui portent le plus d'enjeu.

#### 3.2.3 Reporting et comptes rendus

Le suivi a donné lieu à deux formes de restitution.

Des **points d'avancement périodiques** avec le tuteur et l'équipe, préparés à partir du dashboard et de l'état du tableau Kanban. Chaque point suit le même ordre du jour : ce qui a avancé depuis la dernière fois, ce qui bloque, ce qui est décidé. Les décisions prises y sont consignées, ce qui a permis de tracer les deux arbitrages du § 4.3.

Des **revues de fin de phase**, à chaque jalon, dont le compte rendu prend la forme d'un état documenté du projet : ce que la phase a produit, l'écart constaté et sa cause, ce qui a été décidé, ce qui a été écarté et pourquoi, ce qui reste ouvert. Le **compte rendu de la revue de clôture de P1** est reproduit en annexe E : c'est celui qui a acté la réorientation du § 4.3.2. Les fichiers de suivi du dépôt — journal des runs, fiche de modèle, évaluation de maturité — constituent la trace écrite de ces revues, et c'est à partir d'eux que les dossiers de certification ont été rédigés.

> **Critères couverts (C3.2.2).** ✓ L'outil de suivi, Git pour le flux, `admin.pipeline_run` pour l'exploitation et le dashboard pour la restitution, permet de piloter le projet en cohérence avec la méthodologie Kanban retenue (§ 3.2.1). ✓ Le choix des indicateurs qualitatifs et quantitatifs est argumenté, chaque indicateur étant rattaché à la dimension qu'il pilote (§ 3.2.2). ✓ Les indicateurs permettent de suivre l'avancement — commits, couverture, statut des runs —, le respect des délais — jalons tenus, écart de charge — et la maîtrise des coûts — écart de charge et coût d'infrastructure engagé. ✓ Des reportings et des comptes rendus de réunion sont réalisés, sous forme de points d'avancement périodiques et de revues de fin de phase ; le **compte rendu de la revue de clôture de P1 est reproduit en annexe E** (§ 3.2.3). Le tableau de bord est renseigné : les valeurs relevées des indicateurs figurent au § 3.2.2.

## 4. C3.3 — Constituer et piloter l'équipe

**Rappel de périmètre.** Le projet a été mené par une seule personne. Le pilotage réellement exercé est celui des **parties prenantes**, documenté au § 4.2.1. Le dimensionnement d'équipe et le plan de compétences valent pour le **scénario d'industrialisation**, et sont désignés comme tels.

### 4.1 — C3.3.1 : Plan de développement des compétences

**Livrable : un plan de développement des compétences.**

#### 4.1.1 Compétences à mobiliser

Le déploiement de la solution mobilise quatre familles de compétences : l'**ingénierie de données**, avec SQL, ETL et la connaissance d'Oracle et de PostgreSQL ; l'**apprentissage automatique**, pour la classification, la calibration et l'évaluation ; l'**analyse métier**, pour la modélisation par domaine et la restitution ; la **sécurité et la conformité**, pour le RGPD, le chiffrement et la gestion des accès.

#### 4.1.2 Grille d'évaluation des compétences

La grille compare le niveau d'une équipe type de déploiement au niveau requis par le projet.

| Compétence | Niveau actuel | Niveau requis | Écart |
|---|---|---|---|
| SQL et modélisation dimensionnelle | Confirmé | Confirmé | — |
| ETL et orchestration | Intermédiaire | Confirmé | Modéré |
| ML classique | Confirmé | Confirmé | — |
| Apprentissage profond, transformeurs | Débutant | Confirmé | **Fort** |
| Sécurité et RGPD | Intermédiaire | Confirmé | Modéré |
| Restitution et visualisation | Intermédiaire | Confirmé | Modéré |

**Commentaire de la grille.** Trois enseignements en ressortent. Le socle est acquis : les compétences qui portent l'essentiel de la valeur, SQL, modélisation et ML classique, sont au niveau requis, ce qui rend le déploiement réaliste sans recrutement. L'écart critique est isolé sur l'**apprentissage profond**, qui est aussi la compétence la plus rare et la plus longue à acquérir ; c'est cet écart qui a pesé dans la décision de garder en production un modèle classique plutôt qu'un transformeur (§ 4.3.1), une décision qui a autant réduit un risque de compétence qu'un coût de déploiement. Les trois écarts modérés, enfin, relèvent de la montée en compétence sur un outillage existant plutôt que d'un apprentissage nouveau : ils se comblent par la pratique accompagnée, pas par une formation longue.

#### 4.1.3 Plan de développement et formations préconisées

Quatre actions couvrent les quatre écarts. **Priorité haute, l'apprentissage profond** : formation aux transformeurs complétée de programmation en binôme sur le modèle existant, en ligne et avec mentorat interne. **Priorité moyenne, l'ETL avancé** : montée en compétence sur l'orchestrateur — déploiements, planification, reprise sur incident — par la documentation et un atelier. **Priorité moyenne, la sécurité et le RGPD** : sensibilisation et revue avec un juriste, en atelier et avec accompagnement juridique. **Priorité basse, la restitution** : auto-formation guidée aux bonnes pratiques de visualisation, accessibilité comprise.

Le plan est séquencé selon la priorité : l'écart fort d'abord, parce qu'il conditionne l'évolution du produit, les écarts modérés ensuite, au fil des lots qui les mobilisent. Il s'articule avec le service des ressources humaines pour la partie formation externe et le suivi des acquis. La grille et le plan complets figurent en annexe F.

#### 4.1.4 Prise en compte du handicap dans les modalités de formation

Les modalités sont adaptées aux situations de handicap : supports accessibles avec un contraste suffisant et un sous-titrage des sessions enregistrées, temps supplémentaire lors des évaluations, et possibilité de suivre à distance pour lever une contrainte de déplacement. Ces aménagements sont définis avec la personne concernée et le service des ressources humaines, et non appliqués par défaut.

> **Critères couverts (C3.3.1).** ✓ Les compétences à mobiliser sont identifiées, en quatre familles (§ 4.1.1). ✓ Une grille des compétences actuelles et à acquérir est fournie et **commentée**, le commentaire reliant l'écart critique à une décision d'architecture (§ 4.1.2, annexe F). ✓ Un plan de développement adapté est établi et détaillé, séquencé par priorité (§ 4.1.3). ✓ Des formations sont préconisées selon les besoins du projet et les profils. ✓ Les modalités prennent en considération les spécificités liées au handicap, par aménagement des supports, du temps et des conditions de suivi (§ 4.1.4).

### 4.2 — C3.3.2 : Outils de communication et managériaux

**Livrable : les outils de communication et managériaux utilisés.**

#### 4.2.1 Le pilotage réellement exercé : les parties prenantes

Le projet n'a pas comporté d'équipe à encadrer, mais il a comporté des interlocuteurs à tenir informés, à consulter et à faire décider. C'est cette animation qui a été réellement conduite.

| Interlocuteur | Rôle dans le projet | Routine associée |
|---|---|---|
| Tuteur | Cadrage, arbitrages, validation des orientations | Points d'avancement périodiques |
| Équipe et collègues | Regard technique, retours d'usage | Échanges lors des points, sollicitations ponctuelles |
| Référents métier et DBA | Contraintes et validation du besoin | Entretiens de cadrage, puis consultation à la demande |

Chaque point d'avancement suit le même ordre du jour, ce qui rend les échanges courts et les décisions traçables : avancement depuis le dernier point, blocages, décisions à prendre. Les arbitrages du § 4.3 ont été préparés et tranchés dans ce cadre.

#### 4.2.2 Répartition de la charge dans le scénario d'industrialisation

La charge est répartie par la matrice RACI du § 3.1.4. La ventilation de la charge par rôle, détaillée en annexe C, montre une répartition effective sur les quatre rôles : 40 % pour l'ingénieur données, 28 % pour l'analyste métier, 20 % pour l'ingénieur ML et 12 % pour le chef de projet. L'écart en faveur de l'ingénieur données tient à la nature du produit, dont les lots de collecte et de sécurité concentrent la charge technique ; il est assumé et surveillé, l'équilibrage strict n'étant pas un objectif en soi sur un projet de cette nature.

#### 4.2.3 Outils collaboratifs et routines managériales

| Outil ou routine | Usage | Justification |
|---|---|---|
| Git et revue de code | Collaboration technique et qualité | Traçabilité, revue par les pairs, historique partagé |
| Tableau Kanban | Visualisation du flux de travail | Cohérent avec la méthodologie ; la charge de chacun est visible de tous |
| Point d'avancement court | Suivi régulier | Léger, adapté à une équipe distribuée, décisions consignées |
| Revue de fin de phase | Validation d'un jalon | Décision collégiale, alignement sur la suite |
| Documentation partagée | Référentiel commun | Intégration rapide d'un arrivant, source de vérité unique |

#### 4.2.4 Contexte multiculturel et international

Une équipe data est fréquemment distribuée et internationale. Trois mesures y répondent. La **communication asynchrone est le mode par défaut**, la synchrone étant réservée aux décisions : c'est ce qui permet de travailler à travers des fuseaux horaires sans exclure personne. La **documentation prime sur la transmission orale**, ce qui neutralise les écarts de maîtrise de la langue de travail : un texte se relit, une réunion non. Et les **conventions sont explicites** — langue partagée pour les commits et la documentation, formats de date et d'unité normalisés — parce que ce sont les implicites qui produisent les malentendus dans un contexte multiculturel.

#### 4.2.5 Prise en compte du handicap

L'intégration prévoit un poste de travail adapté et des outils collaboratifs accessibles, compatibles avec les lecteurs d'écran et suffisamment contrastés. La primauté de l'écrit et de l'asynchrone, retenue pour le contexte international, sert directement l'accessibilité : elle laisse à chacun la maîtrise de son rythme et de son canal.

> **Critères couverts (C3.3.2).** ✓ La charge de travail est répartie sur l'ensemble de l'équipe, par la matrice RACI et vérifiée par la ventilation chiffrée de l'annexe C : les quatre rôles portent respectivement 40 %, 28 %, 20 % et 12 % de la charge, la répartition et son déséquilibre assumé étant explicités (§ 4.2.2). ✓ Les outils collaboratifs et les routines managériales sont détaillés et justifiés, pour le pilotage réellement exercé auprès des parties prenantes comme pour le scénario d'équipe (§ 4.2.1 et § 4.2.3). ✓ Les spécificités d'un contexte multiculturel et international sont intégrées, par la primauté de l'asynchrone et de l'écrit et l'explicitation des conventions (§ 4.2.4). ✓ Les personnes en situation de handicap sont prises en compte, sur le poste de travail comme sur les modes de communication (§ 4.2.5).

### 4.3 — C3.3.3 : Cas d'arbitrage rencontrés

**Livrable : la présentation d'un cas d'arbitrage rencontré au cours du projet.**

Deux arbitrages sont présentés. Le premier porte sur une décision d'architecture, le second sur un écart entre le prévisionnel et l'état réel du projet. Tous deux ont été tranchés en cours de projet.

#### 4.3.1 Premier arbitrage : quel modèle mettre en production ?

**La problématique.** Le projet dispose de deux classifieurs : un LinearSVC calibré, léger et déjà intégré au pipeline, et un transformeur XLM-RoBERTa fine-tuné, plus récent. Faut-il promouvoir le transformeur en production ?

**Les conséquences d'un mauvais choix.** Promouvoir le transformeur sans gain réel alourdirait le produit de 2,1 Go et d'un moteur d'inférence supplémentaire, chez chaque client, pour une performance qui n'est pas établie comme supérieure. Écarter à tort un meilleur modèle priverait en revanche la solution d'un gain de qualité sur les domaines réglementés.

**Les options.**

| Option | Avantages | Inconvénients |
|---|---|---|
| **A** — Promouvoir le transformeur | Meilleure calibration ; meilleur rappel sur les domaines réglementés | Justesse inférieure ; 2,1 Go à déployer ; non intégré au traitement par lots |
| **B** — Garder le LinearSVC | Meilleure justesse ; quelques mégaoctets ; déterministe ; déjà intégré | Calibration moins fine |
| **C** — Faire cohabiter les deux | Cumule les forces des deux modèles | Double la maintenance et la surface de test |

**L'outil d'aide à la décision.** Les trois options ont été notées sur cinq critères pondérés selon leur importance pour un produit destiné à être installé chez des clients. Chaque option est notée de 1 à 5.

| Critère | Poids | A — Transformeur | B — LinearSVC | C — Hybride |
|---|---:|---:|---:|---:|
| Justesse de classification | 30 % | 3 | **5** | 5 |
| Coût et simplicité de déploiement | 25 % | 1 | **5** | 1 |
| Intégration au pipeline existant | 20 % | 1 | **5** | 2 |
| Calibration et fiabilité de la confiance | 15 % | 5 | 3 | 5 |
| Maintenabilité et déterminisme | 10 % | 2 | **5** | 1 |
| **Score pondéré** | | **2,3** | **4,7** | **3,0** |

**La décision et son argumentation.** L'option B est retenue. Trois raisons la fondent. Sur la justesse, la métrique décisive pour l'usage, le LinearSVC devance le transformeur. Le coût de déploiement de ce dernier, 2,1 Go et un moteur d'inférence, est disproportionné pour un produit dont l'argument est d'être installable chez n'importe quel client PeopleSoft. Enfin, le LinearSVC ne demande aucun GPU et est déjà intégré au scoring batch, ce qui achève l'arbitrage en sa faveur sur les critères opérationnels ; le transformeur redeviendra promouvable si une évaluation dédiée le justifie.

La comparaison chiffrée complète des deux modèles figure en annexe G.

**La décision résout-elle la problématique ?** Oui, et sur les deux plans. Elle fixe le modèle de production, ce qui débloque l'industrialisation. Et elle transforme le transformeur en axe de recherche assumé, rattaché au Bloc 5, promouvable si une comparaison équitable le justifie un jour. La décision est tracée dans la documentation de classification et dans la fiche de modèle.

#### 4.3.2 Second arbitrage : que faire d'un indicateur qui ne discrimine pas ?

**La problématique.** En phase P1, l'analyse a révélé que le score d'archivabilité était quasi constant : la grande majorité des actifs portaient la valeur de base, faute de signal d'usage exploitable dans la source. L'indicateur devait pourtant être au cœur de la recommandation d'archivage. L'écart entre le prévisionnel et l'état réel du projet était donc frontal, et il s'est traduit par un dépassement de charge sur P1, la phase la plus longue du planning.

**Les conséquences d'un mauvais choix.** Publier le score tel quel aurait donné une recommandation d'apparence quantitative et de contenu vide. Chercher à obtenir le signal manquant supposait une extension du périmètre d'accès à la source, hors de portée dans les délais. Abandonner la recommandation d'archivage aurait vidé le projet de sa finalité.

**Les options et la décision.** Trois voies s'ouvraient : obtenir les statistiques d'accès aux tables, ce qui dépendait d'une autorisation externe et d'un délai incompatible avec les jalons ; publier le score en l'état, au prix d'une recommandation non fondée ; ou **réorienter la recommandation vers des critères effectivement disponibles**. C'est la troisième qui a été retenue. La recommandation d'archivage a été reconstruite sur la volumétrie, la sensibilité de la donnée et les obligations de rétention, et éclatée en sept stratégies différenciées plutôt qu'en un score unique. La limite d'origine, elle, est documentée comme telle dans le dossier du Bloc 2 et n'est pas présentée comme un résultat.

Cet arbitrage illustre la logique de suivi décrite au § 3.2.2 : c'est la dérive de planning sur P1, deux mois pour une phase cible d'un mois, qui a rendu la décision nécessaire, et le registre des risques qui en avait anticipé la cause, l'absence de signal d'usage dans la source.

> **Critères couverts (C3.3.3).** ✓ La problématique qui nécessite un arbitrage est exposée, avec ses conséquences potentielles, pour les deux cas présentés (§ 4.3.1 et § 4.3.2). ✓ Les options possibles pour y remédier sont détaillées, trois pour chaque cas, avec leurs avantages et leurs inconvénients. ✓ La décision d'arbitrage est argumentée et résout la problématique, en fixant le modèle de production dans le premier cas et en reconstruisant la recommandation d'archivage dans le second. Un **outil d'aide à la décision** est mobilisé, sous la forme d'une grille multicritère pondérée (§ 4.3.1), et le second arbitrage procède explicitement de **l'analyse de l'écart entre le prévisionnel et l'état du projet à date** (§ 4.3.2).

## 5. C3.4 — Veiller et agir de façon responsable

### 5.1 — C3.4.1 : Méthodologie de veille

**Livrable : une méthodologie de veille.**

#### 5.1.1 Choix de la méthodologie de recueil

La veille combine trois canaux, choisis pour leur rapport entre le signal obtenu et l'effort consenti.

La **veille technique** porte sur la littérature et les bibliothèques du domaine — calibration des modèles, fonctions de perte adaptées aux classes déséquilibrées, transformeurs multilingues — par les publications de référence et les journaux de version, qui signalent les changements de comportement avant qu'ils ne cassent un pipeline.

La **veille réglementaire et tarifaire** consomme des sources externes rejouables plutôt que des synthèses : l'API publique de tarification du fournisseur de stockage pour les coûts, les textes de référence pour le cadre juridique. Le critère de choix est la vérifiabilité, car une source interrogeable par programme peut être citée, datée et réinterrogée, ce qu'une note de blog ne permet pas.

La **veille outillée** automatise partiellement le premier niveau : le module de collecte tarifaire rafraîchit les coûts à la demande, ce qui transforme une veille manuelle et oubliable en dépendance versionnée du projet.

**Bénéfice attendu :** des décisions techniques et économiques ancrées dans des sources réelles et actualisables, plutôt que dans des constantes figées au moment du développement.

#### 5.1.2 Résultat d'une action de veille et impact sur les pratiques métier

**Première action.** La veille technique sur la calibration des modèles a conduit à mesurer l'erreur de calibration et à adopter une confiance graduée plutôt qu'une valeur forfaitaire. **Impact sur les pratiques métier :** les scores de confiance affichés au décideur sont devenus interprétables. Un score de 90 % signifie désormais qu'environ 90 % des classifications de ce niveau sont correctes, ce qui change la manière dont l'analyste priorise ses vérifications. Sans cette veille, le dispositif de revue aurait reposé sur un chiffre décoratif.

**Seconde action.** La veille tarifaire a remplacé des coûts de stockage estimés, de l'ordre de 0,276 $ par gigaoctet et par an, par des tarifs relevés sur l'API du fournisseur, soit 0,2120 $ pour le stockage actif et 0,0216 $ pour l'archive. **Impact sur les pratiques métier :** tout le calcul de retour sur investissement du Bloc 2 repose désormais sur des valeurs sourcées, datées et rejouables. Une recommandation d'archivage chiffrée sur des coûts inventés n'aurait pas résisté à la première question d'un contrôleur de gestion.

> **Critères couverts (C3.4.1).** ✓ Le choix de la méthodologie de recueil de l'information est argumenté avec les bénéfices attendus : trois canaux complémentaires — technique, réglementaire et tarifaire, outillé — avec pour critère de sélection la vérifiabilité et la rejouabilité des sources, et une automatisation partielle qui inscrit la veille dans le code plutôt que dans une intention (§ 5.1.1). ✓ Le résultat de deux actions de veille est présenté et permet d'identifier ✓ l'impact engendré sur les pratiques métier : interprétabilité des scores de confiance pour la première, fiabilisation de l'ensemble du chiffrage économique pour la seconde (§ 5.1.2).

### 5.2 — C3.4.2 : Plan d'actions RSE, sécurité, éthique et confidentialité

**Livrable : un plan d'actions relatif aux enjeux RSE, de sécurité, d'éthique et de confidentialité.**

#### 5.2.1 Les enjeux de la science des données pour ce projet

**Environnement.** Le stockage de données inactives consomme de l'énergie en continu. L'archivage vers un palier froid réduit cette empreinte, et le rapport de coût de 9,8 entre les deux paliers en donne une mesure indirecte. À cela s'ajoute la sobriété du modèle : un classifieur de quelques mégaoctets consomme, à l'entraînement comme à l'inférence, sans commune mesure avec un transformeur de 2,1 Go.

**Confidentialité.** Les métadonnées collectées peuvent contenir des données personnelles, ce qui place le projet dans le champ du RGPD.

**Éthique de l'intelligence artificielle.** Un modèle qui surévalue sa propre performance induit le décideur en erreur, et l'erreur porte ici sur des décisions d'archivage potentiellement irréversibles. Publier une métrique flatteuse plutôt que la performance réelle serait un manquement de fond, pas un détail de présentation.

**Sécurité.** L'accès à une base de production est en soi un risque, qu'il faut réduire au strict nécessaire.

**Dimension sociale.** La responsabilité sociétale ne se limite pas à l'environnement. Trois volets sont traités ailleurs dans ce dossier et rattachés ici : l'accessibilité du livrable et des conditions de travail (§ 3.1.6), l'adaptation des modalités de formation aux situations de handicap (§ 4.1.4), et l'intégration d'un contexte multiculturel par la primauté de l'écrit et de l'asynchrone (§ 4.2.4).

#### 5.2.2 Arbitrages de priorisation

Face à des ressources limitées, la **confidentialité et l'éthique ont été traitées en premier**, avant l'optimisation fine de l'empreinte environnementale. Deux raisons à cet ordre. Ces deux enjeux portent un risque immédiat, légal pour l'un, de confiance pour l'autre, alors que le bénéfice environnemental du projet est acquis par nature : archiver réduit la consommation, que l'on mesure ce gain ou non. Et une donnée personnelle exposée est un dommage irréversible, là où une mesure d'empreinte carbone différée reste rattrapable. Mieux vaut une donnée bien protégée qu'un gain énergétique finement quantifié.

#### 5.2.3 Le plan d'actions

| Sujet | Action mise en œuvre | Statut | Délai |
|---|---|---|---|
| **Confidentialité** | Masquage des données personnelles dans les exports et chiffrement au repos en base | Réalisé | Phases P2 et P4 |
| **Sécurité** | Accès Oracle en lecture seule ; comptes PostgreSQL séparés en lecture et écriture, principe du moindre privilège | Réalisé | Phase P4 |
| **Éthique de l'IA** | Labels générés par LLM local, échantillon validé par un expert ; métriques sur holdout indépendant ; affichage systématique de la confiance | Réalisé | Phases P0 à P3 |
| **Environnement** | Recommandations d'archivage réduisant le volume en stockage actif ; choix d'un modèle de production léger contre un transformeur de 2,1 Go | Réalisé | Phases P1 et P4 |
| Confidentialité — suite | Externalisation des secrets et des clés vers un coffre dédié | À faire | Au premier déploiement client, lot « sécurité et conformité » |
| Éthique — suite | Évaluation du modèle sur un jeu de test étiqueté indépendant, avec matrice de confusion par domaine | À faire | Sous trois mois, avant toute promotion de modèle |
| Environnement — suite | Quantification de l'empreinte évitée, en kilowattheures par téraoctet archivé | À faire | Sous six mois, une fois un historique de runs disponible |

Quatre actions sur sept sont réalisées et vérifiables dans le dépôt. Les trois restantes sont datées et affectées à une échéance, non renvoyées à une intention générale. Le plan complet, avec le statut de chaque ligne, figure en annexe H.

> **Critères couverts (C3.4.2).** ✓ Les enjeux de la science des données en termes de RSE sont détaillés, sur les quatre dimensions attendues : environnement, confidentialité, éthique de l'IA et sécurité (§ 5.2.1). ✓ Les arbitrages de priorisation retenus pour établir le plan d'actions sont précisés et justifiés, par le caractère immédiat et irréversible du risque plutôt que par l'ampleur du bénéfice (§ 5.2.2). ✓ Le plan d'actions précise, pour chaque ligne, ✓ le sujet traité, ✓ l'action mise en œuvre et ✓ le délai, complétés du statut de réalisation (§ 5.2.3).

## 6. Conclusion

Le projet a été conduit de bout en bout, du cadrage à la livraison, par une personne à disponibilité partielle, avec l'appui de parties prenantes sollicitées à intervalles réguliers.

**Cadrer et dimensionner.** Problématique, objectifs, cadre RGPD, contraintes et enjeux RSE sont posés, les points de vigilance formalisés en registre des risques. Le dimensionnement distingue le réalisé — 60 jours-homme sur 173 jours calendaires — du projeté pour une industrialisation — 150 jours-homme et un budget indicatif de 84 000 € HT. L'analyse de faisabilité établit que le dossier économique repose sur le coût évité de la cartographie manuelle, non sur la seule économie de stockage.

**Planifier et suivre.** La méthodologie Kanban est justifiée par la nature exploratoire du projet et par sa taille. Le planning est daté par les runs du pipeline et l'historique Git, découpé en six phases et en lots, jalonné par quatre échéances externes dont les deux échues sont tenues. Le suivi couvre l'avancement, les délais et les coûts, et s'accompagne de points d'avancement et de revues de fin de phase.

**Constituer et piloter.** Le plan de compétences isole un écart critique, l'apprentissage profond, et le relie à une décision d'architecture. Deux arbitrages sont documentés : le choix du modèle de production, tranché par une grille multicritère pondérée, et la réorientation de la recommandation d'archivage, née d'un écart entre le prévisionnel et le réel.

**Veiller et agir de façon responsable.** La veille est outillée et ses résultats ont modifié des pratiques : scores de confiance devenus interprétables, coûts estimés remplacés par des tarifs sourcés. Quatre des sept actions du plan RSE sont réalisées et vérifiables ; les trois autres sont datées.

Une ligne directrice traverse ces décisions : **ne jamais laisser un dispositif automatique décider seul de ce qui est irréversible**. C'est elle qui a fait retenir un modèle simple et vérifiable plutôt qu'un modèle plus impressionnant, imposé la revue humaine sur les classifications incertaines, et fait que la solution recommande sans jamais exécuter.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

## Annexes (hors décompte de pages)

Les annexes font l'objet d'un document séparé, `BLOC3_Annexes.docx`.

- **A. Planning détaillé** — phases P0 à P5, diagramme de Gantt, jalons de certification, charge par phase.
- **B. Matrice RACI** — équipe cible du scénario d'industrialisation.
- **C. Chiffrage détaillé** — charge et coût par lot, justification économique, ventilation par rôle.
- **D. Sommaire des spécifications** — exigences fonctionnelles et techniques, critères d'acceptation.
- **E. Compte rendu type de revue de fin de phase** — modèle appliqué, exemple de la clôture de P1.
- **F. Grille de compétences et plan de formation** — niveaux actuels et requis, actions, modalités, priorités.
- **G. Cas d'arbitrage** — comparaison chiffrée des deux modèles et grille multicritère pondérée.
- **H. Plan d'actions RSE, sécurité, éthique et confidentialité** — sujets, actions, statuts, délais.
- **I. Correspondance grille d'évaluation / dossier** — chaque critère rapporté à son paragraphe.
