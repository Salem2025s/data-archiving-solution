# BLOC 3 — Annexes

**Titre RNCP 39586 · Bloc 3 — Élaborer et piloter un projet data**
**Candidat :** HAOUARI Salem · **Date :** 17/08/2026
**Annexes au dossier écrit, hors décompte de pages**

Ces annexes détaillent les livrables de pilotage référencés dans le dossier. Le planning et le suivi s'appuient sur des traces vérifiables : la table `admin.pipeline_run` de l'entrepôt, qui horodate chaque exécution, et l'historique Git du dépôt.

## Annexe A — Planning détaillé

Le projet a débuté le 9 mars 2026. Les dates de phase ne sont pas reconstruites : les premières sont établies par les runs journalisés dans `admin.pipeline_run`, les suivantes par l'historique Git, le dépôt ayant été formalisé en juin. La charge de l'annexe A.3, en revanche, est une estimation reconstituée, signalée comme telle.

![Diagramme de Gantt du projet : six phases réelles de mars à août 2026, datées par les runs du pipeline et l'historique Git.](img/bloc3_gantt.png)

### A.1 Phases et lots de travail

| Phase | Période | Lots de travail | Jalon de vérification |
|---|---|---|---|
| **P0** — Cadrage et collecte | 09/03 → 31/03 | Entretiens de cadrage · connexion Oracle · extraction du dictionnaire de données · premiers cycles de chargement | Runs 3 (13/03) et 4 (23/03) |
| **P1** — Modélisation et analyse | 01/04 → 31/05 | Modèle en étoile · classification par domaine · comparaison inter-runs · projection de ROI | Runs 5 (22/04) et 6 (31/05) |
| **P2** — Sûreté et fiabilité | 01/06 → 09/06 | Mécanismes de reprise · journal d'audit · masquage des données personnelles · calibration du modèle | Commits `phase0`, `phase1` |
| **P3** — Apprentissage profond | 09/06 → 19/06 | Fine-tuning du transformeur, versions 1 et 3 · page de test interactif | Commits `xlmr`, `page de test` |
| **P4** — Sécurité et sources externes | 07/07 → 17/07 | Tarifs par API · chiffrement `pgcrypto` · rôles séparés · refonte du dashboard · console SQL | Commits `extract`, `security`, `console SQL` |
| **P5** — Certification | 14/07 → 29/08 | Dossiers des Blocs 1, 2, 3 et 5 · annexes · préparation de la soutenance | Dépôts des semaines 29, 31 et 34 |

### A.2 Jalons externes de certification

| Jalon | Échéance | Statut |
|---|---|---|
| Dépôt du Bloc 1, rendu écrit | Semaine 29 — 13 au 17/07/2026 | Tenu |
| Dépôt du Bloc 2, rendu écrit | Semaine 31 — 27 au 31/07/2026 | Tenu |
| Dépôt du Bloc 3, rendu écrit | Semaine 34 — 17 au 21/08/2026 | En cours |
| Soutenance orale du bloc de spécialité | Semaines 36 à 40 — 01 au 29/09/2026 | À venir |

### A.3 Charge estimée par phase

Charge **reconstituée a posteriori** à partir des dates de phase, des runs journalisés et de la densité de l'historique Git. Il ne s'agit pas d'un relevé de temps.

| Phase | Charge estimée | Part du total |
|---|---:|---:|
| P0 — Cadrage et collecte | 9 j·h | 15 % |
| P1 — Modélisation et analyse | 22 j·h | 37 % |
| P2 — Sûreté et fiabilité | 5 j·h | 8 % |
| P3 — Apprentissage profond | 6 j·h | 10 % |
| P4 — Sécurité et sources externes | 6 j·h | 10 % |
| P5 — Certification | 12 j·h | 20 % |
| **Total** | **60 j·h** | **100 %** |

La période compte 173 jours calendaires, soit environ 124 jours ouvrés hors congés : la charge correspond donc à un taux d'occupation de l'ordre de 48 %, cohérent avec une disponibilité partielle et discontinue. La coupure de dix-sept jours entre P3 et P4, du 20 juin au 6 juillet, correspond à une interruption sans activité sur le projet.

### A.4 Méthodologie de conduite

Kanban, en flux continu — *à faire*, *en cours*, *fait* — avec limitation du travail en cours, jalonné par les échéances de certification. Le choix et ses bénéfices sont argumentés au § 3.1.1 du dossier.

## Annexe B — Matrice RACI du scénario d'industrialisation

Pour un déploiement chez un client, la solution serait portée par une équipe de trois à quatre personnes. R désigne celui qui réalise, A celui qui approuve, C celui qui est consulté, I celui qui est informé.

| Activité | Chef de projet data | Ingénieur données | Ingénieur ML | Analyste métier |
|---|---|---|---|---|
| Cadrage et spécifications | A | C | C | **R** |
| Collecte et ETL Oracle | I | **R** | C | I |
| Modélisation ML et scoring | A | C | **R** | C |
| Dashboard et restitution | I | C | I | **R** |
| Sécurité et conformité RGPD | A | **R** | I | C |
| Recette et validation métier | A | I | I | **R** |
| Documentation projet | C | C | C | **R** |

**Équilibrage de la charge.** Chaque membre porte un domaine principal en tant que réalisateur, tout en étant consulté sur les interfaces avec les domaines voisins, ce qui évite à la fois la surcharge d'un point de passage obligé et le cloisonnement de chacun dans son périmètre. La ventilation chiffrée figure en annexe C.3.

## Annexe C — Chiffrage détaillé du déploiement

### C.1 Charge et coût par lot

| Lot | Charge | Coût | Rôle porteur |
|---|---:|---:|---|
| Cadrage et spécifications | 15 j·h | 7 500 € | Analyste métier |
| Collecte et ETL sur l'instance client | 40 j·h | 20 000 € | Ingénieur données |
| Modélisation et scoring | 30 j·h | 15 000 € | Ingénieur ML |
| Dashboard et restitution | 25 j·h | 12 500 € | Analyste métier |
| Sécurité et conformité RGPD | 20 j·h | 10 000 € | Ingénieur données |
| Recette et documentation | 20 j·h | 10 000 € | Analyste métier et chef de projet |
| **Sous-total charge** | **150 j·h** | **75 000 €** | |
| Infrastructure : base managée et hébergement, 5 mois | — | 1 000 € | |
| Provision pour aléas, 10 % de la charge et de l'infrastructure | — | 7 600 € | |
| **Budget indicatif** | | **≈ 84 000 € HT** | |

*Hypothèse de valorisation : taux journalier moyen de 500 € HT, ordre de grandeur du marché français pour des profils data confirmés en prestation. Ce taux est une hypothèse de chiffrage et non un tarif négocié.*

**Délai.** 150 jours-homme sur une équipe de trois à quatre personnes représentent environ deux mois de travail effectif. Les dépendances entre lots — la collecte conditionne la modélisation, qui conditionne la restitution — et le temps de recette portent le délai calendaire à quatre à cinq mois.

### C.2 Justification économique

Le budget ne se justifie pas par la seule économie de stockage. Au taux mesuré de 195 $ par téraoctet archivé et par an, une base ERP de quelques téraoctets ne dégage que quelques centaines de dollars d'économie annuelle.

La justification repose sur le **coût évité de la cartographie manuelle**. Cartographier 167 260 actifs à la main, à raison de trente secondes par actif pour un expert du progiciel, représente environ 1 400 heures, soit de l'ordre de 175 jours-homme sur une base de 8 heures. Au même taux journalier, cela dépasse 85 000 € pour un seul patrimoine, et le résultat serait figé le jour de sa production, alors que la solution se rejoue à chaque exécution. S'y ajoutent deux bénéfices non monétarisés : la réduction de la dépendance à quelques experts, et la capacité à répondre à une demande de conformité sur l'origine et la rétention des données.

### C.3 Ventilation de la charge par rôle

| Rôle | Lots portés | Charge | Part |
|---|---|---:|---:|
| Ingénieur données | Collecte et ETL · Sécurité et conformité | 60 j·h | 40 % |
| Analyste métier | Dashboard · moitié du cadrage · moitié de la recette | 42 j·h | 28 % |
| Ingénieur ML | Modélisation et scoring | 30 j·h | 20 % |
| Chef de projet data | Moitié du cadrage · moitié de la recette et documentation | 18 j·h | 12 % |
| **Total** | | **150 j·h** | **100 %** |

La charge se répartit sur les quatre rôles, avec un écart marqué en faveur de l'ingénieur données. Cet écart est assumé : sur un produit dont la valeur tient d'abord à la collecte et à la sécurisation d'une source ERP, ce sont ces deux lots qui concentrent la charge technique. Le chef de projet, à 12 %, intervient sur le cadrage et la recette, ses autres activités relevant du pilotage et non de la production. La répartition est un point de surveillance du plan de charge, non un équilibre à atteindre coûte que coûte.

## Annexe D — Sommaire des spécifications

La documentation projet tient lieu de cahier des charges vivant (§ 2.3.2). Le tableau ci-dessous en donne le sommaire : les exigences fonctionnelles décrivent ce que le système doit faire, les exigences techniques comment il le fait. Chaque ligne renvoie au document qui la porte dans le dépôt.

### D.1 Exigences fonctionnelles

| Réf. | Exigence | Critère d'acceptation | Document |
|---|---|---|---|
| EF-1 | Collecter les métadonnées de l'instance source sans écrire dessus | Réconciliation source / entrepôt à écart nul ; compte source en lecture seule vérifié | `docs/A_connexion_preparation` |
| EF-2 | Rattacher chaque actif à un domaine métier | 100 % des actifs classés, avec un niveau de confiance par actif | `docs/B_classification_ml` |
| EF-3 | Signaler les classifications à vérifier | Marqueur de revue exposé et filtrable dans la restitution | `docs/B_classification_ml` |
| EF-4 | Chiffrer le coût de stockage par domaine | Coût annuel calculé sur des tarifs sourcés et horodatés | `docs/E1_gains_stockage` |
| EF-5 | Recommander une stratégie d'archivage par actif | Stratégie différenciée, distinguant conservation réglementaire et archivage | `docs/D_regles_archivage` |
| EF-6 | Restituer sans installation côté utilisateur | Accès navigateur, export tableur et requêtes libres en lecture seule | `docs/E4_repartition_couts` |

### D.2 Exigences techniques

| Réf. | Exigence | Critère d'acceptation | Document |
|---|---|---|---|
| ET-1 | Architecture en couches, du brut au servi | Trois schémas distincts, la couche brute restant fidèle à la source | Dossier Bloc 1 |
| ET-2 | Rejouabilité de toute analyse | Identifiant de run porté par chaque table et filtré par chaque requête | `docs/A_connexion_preparation` |
| ET-3 | Protection des données personnelles | Masquage dans les exports, chiffrement au repos | Dossier Bloc 1 |
| ET-4 | Moindre privilège | Comptes de lecture et d'écriture séparés, vérifiés par la pratique | Dossier Bloc 1 |
| ET-5 | Substituabilité de la source | Instance déclarée en configuration, aucun identifiant en dur | `config/` |
| ET-6 | Traçabilité du modèle déployé | Version de modèle portée par chaque prédiction, fiche de modèle à jour | `artifacts/production_model_card.md` |

## Annexe E — Compte rendu type de revue de fin de phase

Modèle appliqué à chaque jalon (§ 3.2.3). L'exemple ci-dessous est celui de la revue de clôture de la phase P1.

| Rubrique | Contenu |
|---|---|
| **Phase** | P1 — Modélisation et analyse |
| **Période** | 01/04 → 31/05/2026 |
| **Participants** | Candidat, tuteur |
| **Produit** | Modèle en étoile, classification par domaine des 167 260 actifs, comparaison inter-runs, projection de ROI |
| **Écart constaté** | Durée de deux mois pour une phase cible d'un mois |
| **Cause** | Score d'archivabilité quasi constant, faute de signal d'usage dans la source |
| **Décision prise** | Reconstruire la recommandation d'archivage sur la volumétrie, la sensibilité et les obligations de rétention ; documenter la limite d'origine plutôt que la masquer |
| **Écarté** | Demande d'extension du périmètre d'accès à la source, délai incompatible avec les jalons |
| **Reste ouvert** | Quantification de l'empreinte évitée, reportée au plan RSE |
| **Prochain jalon** | P2 — Sûreté et fiabilité, clôture au 09/06 |

Les revues suivantes ont été tenues selon le même modèle. Leur trace écrite est constituée par les fichiers de suivi du dépôt : journal des runs, fiche de modèle et évaluation de maturité, mis à jour à chaque clôture de phase.

## Annexe F — Grille de compétences et plan de formation

### F.1 Compétences actuelles et requises pour l'équipe cible

| Compétence | Niveau actuel | Niveau requis | Écart |
|---|---|---|---|
| SQL et modélisation dimensionnelle | Confirmé | Confirmé | — |
| ETL et orchestration | Intermédiaire | Confirmé | Modéré |
| ML classique | Confirmé | Confirmé | — |
| Apprentissage profond, transformeurs | Débutant | Confirmé | **Fort, critique** |
| Sécurité et RGPD | Intermédiaire | Confirmé | Modéré |
| Restitution et visualisation | Intermédiaire | Confirmé | Modéré |

**Commentaire.** Le socle est acquis : les compétences qui portent l'essentiel de la valeur sont au niveau requis, ce qui rend le déploiement réaliste sans recrutement. L'écart critique est isolé sur l'apprentissage profond, compétence rare et longue à acquérir ; il a pesé dans la décision de conserver un modèle classique en production (annexe G). Les écarts modérés relèvent de la montée en compétence sur un outillage existant, et se comblent par la pratique accompagnée.

### F.2 Plan de développement des compétences

| Écart | Action de formation | Modalité | Priorité |
|---|---|---|---|
| Apprentissage profond | Formation aux transformeurs, complétée de programmation en binôme sur le modèle existant | En ligne et mentorat interne | Haute |
| ETL avancé | Montée en compétence sur l'orchestrateur : déploiements, planification, reprise sur incident | Documentation et atelier | Moyenne |
| Sécurité et RGPD | Sensibilisation RGPD et revue avec un juriste | Atelier et accompagnement juridique | Moyenne |
| Restitution | Bonnes pratiques de visualisation : accessibilité, choix des représentations | Auto-formation guidée | Basse |

**Prise en compte du handicap.** Supports accessibles, avec contraste suffisant et sous-titrage des sessions enregistrées. Temps supplémentaire lors des évaluations. Possibilité de suivre à distance pour lever une contrainte de déplacement. Ces aménagements sont définis avec la personne concernée et le service des ressources humaines, et non appliqués par défaut.

## Annexe G — Cas d'arbitrage : quel modèle mettre en production ?

**Problématique.** Le projet dispose de deux classifieurs. Faut-il promouvoir le transformeur deep learning en production à la place du modèle classique déjà intégré ?

### G.1 Comparaison chiffrée

| Critère | LinearSVC + Platt, en production | XLM-RoBERTa v3 |
|---|---|---|
| Justesse | **0,907** | 0,838 |
| Macro-F1 | **0,869** en validation croisée, 0,892 en holdout | 0,802 |
| Calibration | Correcte | **0,011** d'erreur de calibration, excellente |
| Rappel sur les domaines réglementés | — | Finance 0,89 · RH 0,94 · Achats 0,91 |
| Poids de déploiement | **Quelques mégaoctets** | 2,1 Go, plus le moteur d'inférence |
| Intégration au traitement par lots | **Oui**, scoring des 167 260 actifs | Non, démonstration interactive seulement |
| Déterminisme et reproductibilité | **Élevé** | Moindre |

### G.2 Grille multicritère pondérée

Chaque option est notée de 1 à 5 sur cinq critères, pondérés selon leur importance pour un produit destiné à être installé chez des clients.

| Critère | Poids | A — Transformeur | B — LinearSVC | C — Hybride |
|---|---:|---:|---:|---:|
| Justesse de classification | 30 % | 3 | **5** | 5 |
| Coût et simplicité de déploiement | 25 % | 1 | **5** | 1 |
| Intégration au pipeline existant | 20 % | 1 | **5** | 2 |
| Calibration et fiabilité de la confiance | 15 % | 5 | 3 | 5 |
| Maintenabilité et déterminisme | 10 % | 2 | **5** | 1 |
| **Score pondéré** | | **2,30** | **4,70** | **3,00** |

### G.3 Options et décision

**Option A — Promouvoir le transformeur.** Meilleure calibration et meilleur rappel sur les domaines réglementés, mais justesse inférieure, 2,1 Go à déployer chez chaque client, et absence d'intégration au traitement par lots.

**Option B — Conserver le LinearSVC.** *Retenue.* Meilleure justesse, quelques mégaoctets, comportement déterministe, déjà intégré au pipeline.

**Option C — Faire cohabiter les deux modèles.** Cumulerait les forces mais doublerait la maintenance et la surface de test.

**Décision argumentée.** Sur la justesse, métrique décisive pour l'usage, le LinearSVC devance le transformeur, 0,907 contre 0,838. Le coût de déploiement de ce dernier est disproportionné pour un produit dont l'argument commercial est d'être installable chez n'importe quel client PeopleSoft. Enfin, le LinearSVC ne demande aucun GPU et est déjà intégré au scoring batch, ce qui achève l'arbitrage en sa faveur sur les critères opérationnels. Le transformeur reste développé comme axe de recherche, rattaché au Bloc 5, et redeviendra promouvable si une évaluation dédiée le justifie. La décision est tracée dans la documentation de classification et dans la fiche de modèle.

## Annexe H — Plan d'actions RSE, sécurité, éthique et confidentialité

| Sujet | Action | Statut | Délai |
|---|---|---|---|
| **Confidentialité** | Masquage des données personnelles dans les exports et chiffrement au repos en base | Réalisé | Phases P2 et P4 |
| **Sécurité** | Accès Oracle en lecture seule ; comptes PostgreSQL séparés en lecture et écriture, moindre privilège | Réalisé | Phase P4 |
| **Éthique de l'IA** | Labels générés par LLM local, échantillon validé par un expert ; métriques sur holdout indépendant ; affichage systématique de la confiance | Réalisé | Phases P0 à P3 |
| **Environnement** | Recommandations d'archivage réduisant le volume en stockage actif ; choix d'un modèle de production léger contre un transformeur de 2,1 Go | Réalisé | Phases P1 et P4 |
| Confidentialité — suite | Externalisation des secrets et des clés vers un coffre dédié | À faire | Court terme, à l'industrialisation |
| Environnement — suite | Quantification de l'empreinte évitée, en kilowattheures par téraoctet archivé | À faire | Moyen terme |
| Éthique — suite | Évaluation sur un jeu de test étiqueté indépendant, avec matrice de confusion par domaine | À faire | Court terme |

**Arbitrage de priorisation.** Face à des ressources limitées, la confidentialité et l'éthique ont été traitées avant l'optimisation fine de l'empreinte environnementale. Ces deux enjeux portent un risque immédiat, légal pour l'un et de confiance pour l'autre, alors que le bénéfice environnemental du projet est acquis par nature. Une donnée personnelle exposée est par ailleurs un dommage irréversible, là où une mesure d'empreinte différée reste rattrapable.

## Annexe I — Correspondance grille d'évaluation / dossier

| Compétence | Critère de la grille | Traité en |
|---|---|---|
| C3.1.1 | La problématique | § 2.1.1 |
| C3.1.1 | Les objectifs et les livrables du projet | § 2.1.2 |
| C3.1.1 | Le cadre réglementaire | § 2.1.3 |
| C3.1.1 | Les contraintes et les points de vigilance | § 2.1.4 et § 2.1.5 |
| C3.1.1 | Les enjeux RSE | § 2.1.6 · § 5.2 |
| C3.1.2 | Les ressources humaines nécessaires | § 2.2.1 |
| C3.1.2 | Les ressources matérielles et logistiques | § 2.2.2 |
| C3.1.2 | Un chiffrage du projet, coût et délai | § 2.2.3 · annexes C.1 et C.3 |
| C3.1.2 | Une analyse de la faisabilité | § 2.2.4 |
| C3.1.3 | Documentation en adéquation avec le cadrage, présentant l'ensemble des caractéristiques | § 2.3.2 · annexe D |
| C3.1.3 | Vocabulaire compréhensible par les parties prenantes | § 2.3.1 et § 2.3.2 |
| C3.2.1 | Choix de la méthodologie justifié avec les bénéfices attendus | § 3.1.1 |
| C3.2.1 | Outil de planification compatible avec la méthodologie | § 3.1.1 · annexe A |
| C3.2.1 | Planning découpé en phases, tâches ou lots | § 3.1.3 · annexe A.1 |
| C3.2.1 | Visualisation des différentes phases | Diagramme de Gantt, § 3.1.3 |
| C3.2.1 | Tâches assignées selon les compétences, matrice RACI | § 3.1.4 · annexe B |
| C3.2.1 | Prise en compte des personnes en situation de handicap | § 3.1.6 |
| C3.2.1 | Points de vigilance soulignés, chemin critique et compétences rares | § 3.1.5 · § 2.1.5 |
| C3.2.2 | Outil de suivi en adéquation avec la méthodologie | § 3.2.1 |
| C3.2.2 | Choix des indicateurs qualitatifs et quantitatifs argumenté | § 3.2.2 |
| C3.2.2 | Suivi de l'avancement, des délais et des coûts | § 3.2.2, valeurs relevées comprises |
| C3.2.2 | Reportings et comptes rendus de réunion | § 3.2.3 · annexe E |
| C3.3.1 | Compétences à mobiliser identifiées | § 4.1.1 |
| C3.3.1 | Grille d'évaluation commentée | § 4.1.2 · annexe F.1 |
| C3.3.1 | Plan de développement établi et détaillé | § 4.1.3 · annexe F.2 |
| C3.3.1 | Formations préconisées selon les besoins et les profils | § 4.1.3 |
| C3.3.1 | Modalités adaptées aux spécificités liées au handicap | § 4.1.4 |
| C3.3.2 | Charge de travail répartie de manière équilibrée | § 4.2.2 · annexes B et C.3 |
| C3.3.2 | Outils collaboratifs et routines managériales détaillés et justifiés | § 4.2.1 et § 4.2.3 |
| C3.3.2 | Contexte multiculturel et international | § 4.2.4 |
| C3.3.2 | Personnes en situation de handicap prises en compte | § 4.2.5 |
| C3.3.3 | Problématique exposée avec ses conséquences potentielles | § 4.3.1 et § 4.3.2 |
| C3.3.3 | Options possibles détaillées | § 4.3.1 et § 4.3.2 · annexe G.3 |
| C3.3.3 | Décision argumentée résolvant la problématique | § 4.3.1 et § 4.3.2 |
| C3.3.3 | Outil d'aide à la décision | Grille multicritère, § 4.3.1 · annexe G.2 |
| C3.3.3 | Analyse de l'écart entre le prévisionnel et l'état à date | § 4.3.2 |
| C3.4.1 | Choix de la méthodologie de recueil argumenté avec les bénéfices | § 5.1.1 |
| C3.4.1 | Résultat d'une action de veille présenté | § 5.1.2 |
| C3.4.1 | Impact engendré sur les pratiques métier | § 5.1.2 |
| C3.4.2 | Enjeux RSE de la science des données détaillés | § 5.2.1 |
| C3.4.2 | Arbitrages de priorisation précisés et justifiés | § 5.2.2 |
| C3.4.2 | Plan précisant le sujet, l'action et les délais | § 5.2.3 · annexe H |
