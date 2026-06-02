# D — Règles d'archivage data-driven : Fiche Métier

> **Statut :** ✅ Complet  
> **Public cible :** Chef de projet, jury PFE, non-technicien

---

## Qu'est-ce qu'on fait dans cette section ?

On transforme les données techniques en **recommandations d'archivage concrètes** : pour chacune des **~16 800 tables qui occupent réellement du stockage** (on écarte les ~150 000 objets logiques PeopleSoft sans données), le système indique quelle stratégie appliquer (archiver, compresser, **conserver pour conformité**...) et **pourquoi**.

Résultat principal : **~8 500 tables totalisant ~6,6 Go sont archivables** — après avoir mis de côté ~0,3 Go que la loi impose de conserver (Finance, RH…).

---

## La démarche data-driven

Au lieu de se fier à un score unique, le moteur analyse **5 dimensions concrètes** de chaque table :

| Dimension | Question posée | Donnée utilisée |
|---|---|---|
| **Volume** | La table est-elle grosse ? | Taille en Mo, nombre de lignes |
| **Ancienneté** | Depuis quand n'a-t-elle pas été touchée ? | Date de dernière analyse Oracle |
| **Sensibilité** | Contient-elle des données personnelles ? | Détection automatique d'emails, identifiants, noms... |
| **Dépendances** | D'autres tables en dépendent-elles ? | Liens hiérarchiques PeopleSoft |
| **Domaine métier** ⭐ | Quelle durée légale de conservation ? | Rétention par domaine (Finance 10 ans, RH 5 ans, IT 1 an…) |

> ⭐ **Nouveauté clé :** le **domaine métier** (issu de la classification, partie B) **pilote désormais la décision**. Une donnée Finance ou RH encore dans sa durée de conservation légale n'est **pas** archivée, là où une donnée IT équivalente l'est. La classification ne sert donc plus seulement au reporting : elle **change l'action**.

> **Découverte importante :** le score d'archivabilité classique ne fonctionnait pas (99,8 % des tables avaient le même score ~45). On s'appuie donc sur les **faits physiques** — c'est plus fiable et plus explicable.

---

## Les 9 stratégies d'archivage

| Stratégie | Quand ? | Action |
|---|---|---|
| **Conservation critique** | ≥ 10 tables en dépendent (pilier structurel) | Ne jamais archiver |
| **Archivage chiffré** | Données personnelles anciennes | Stockage froid + chiffrement (RGPD) |
| **Conservation sécurisée** | Données personnelles actives | Garder + accès contrôlé |
| **Conservation réglementaire** ⭐ | Domaine réglementé encore dans sa durée légale (Finance, RH…) | **Conserver — interdiction d'archiver (conformité)** |
| **Archivage à froid** | Données inactives au-delà de leur durée de conservation | Déplacer vers stockage économique |
| **Compression** | Données moyennement anciennes | Compresser sur place |
| **À évaluer** | Grosse table, âge inconnu | Analyse humaine requise |
| **Conservation** | Données récentes ou peu archivables | Garder en l'état |
| *(Non applicable)* | *(plus utilisée : on ne traite que les tables physiques)* | — |

---

## Le résultat concret (run_id=6)

### Vue d'ensemble (16 828 tables physiques)

| Catégorie | Nb tables |
|---|---|
| **Conservation réglementaire** (Finance/RH/Achats/Ventes dans leur durée légale) | **6 895** |
| **À archiver à froid** | **6 854** |
| À archiver chiffré (PII) | 1 620 |
| Conservation critique (piliers) | 1 135 |
| À conserver (sécurisé / actif / compressé) | 324 |

### Quel domaine archiver — et lequel protéger ?

> **IT & Sécurité** reste le plus gros gisement archivable : **4 590 tables** à archiver à froid (rétention courte, 1 an). C'est la cible n°1.

> À l'inverse, **Finance (5 369 tables), Achats, Ventes** sont massivement **conservés** : leurs données restent dans la fenêtre de conservation légale (10 ans) — les archiver serait une **faute de conformité**. C'est tout l'intérêt d'avoir rendu le domaine décisionnel.

---

## Un exemple concret de recommandation

```
Table : PTIACPTMPLTFQUS (IT & Sécurité)
Taille : 2 215 Mo
Stratégie : ARCHIVAGE À FROID
Rétention : 10 ans
Justification : volume élevé (2215 Mo) ; non analysée depuis +3 ans ;
                aucune dépendance sortante
```

À elle seule, cette table représente 2,2 Go — l'archiver libère immédiatement de l'espace significatif.

---

## La dimension RGPD (conformité)

Le système détecte automatiquement les **données personnelles** (emails, identifiants employés, noms) et les route vers une stratégie dédiée :

- **1 620 tables PII anciennes** → archivage **chiffré** (obligation RGPD)
- **122 tables PII actives** → conservation **sécurisée** (accès contrôlé)

C'est un atout fort du projet : l'archivage respecte la conformité réglementaire dès la conception — désormais **renforcé** par les durées de conservation légales par domaine (`CONSERVATION_REGLEMENTAIRE`).

---

## Ce que ça apporte au projet

1. **Liste d'action immédiate** : les équipes IT et métier savent exactement quoi archiver, sans interpréter de score
2. **Auditabilité** : chaque recommandation est justifiée automatiquement
3. **Conformité RGPD** : les données sensibles sont traitées séparément
4. **Décision pilotée par le domaine** : on archive IT (rétention courte) et on **conserve Finance/RH** (conformité) — la classification métier **change réellement l'action**, pas seulement le reporting
5. **Conformité légale intégrée** : durées de conservation par domaine (`dim_domain_retention`) → aucun archivage prématuré de données réglementées
6. **Exploitable par un agent** : règles formalisées (`dim_archiving_policy` + `dim_domain_retention`) — applicables automatiquement par un futur outil

---

## Limites & signaux explorés

- **Dernière date de modification** : on a tenté de récupérer un vrai « dernier changement » par table (`ALL_TAB_MODIFICATIONS`). **Vérification faite directement dans Oracle : ce signal est quasi inexistant** (47 tables sur 79 633 — Oracle l'efface dès qu'il recalcule les statistiques). On conserve donc la « date de dernière analyse » comme indicateur d'ancienneté.
- **Tables orphelines** : on récupère désormais le **nombre d'objets (vues, procédures) qui dépendent de chaque table** (`ALL_DEPENDENCIES`) — signal riche et fiable (7 210 tables référencées). Une table **très référencée** est un pilier à **conserver** ; une table **orpheline** ancienne devient candidate à l'archivage. *(Actif à la prochaine extraction sous VPN.)*
- **Fréquence de lecture** : on a *testé* — le compte applicatif (SYSADM) n'a accès à **aucune** vue Oracle de statistiques d'accès (toutes renvoient « table inexistante »). Ce n'est donc pas un oubli mais une **permission manquante**. Un **dispositif prêt à l'emploi** est déjà en place (extraction + 6ᵉ règle « ne pas archiver une table encore lue ») : il reste neutre aujourd'hui et **s'activera tout seul** dès qu'un administrateur Oracle accordera l'accès (`GRANT SELECT ON SYS.V_$SEGMENT_STATISTICS TO SYSADM`), sans rien recoder.
- **Durées légales par défaut** : les rétentions par domaine (Finance 10 ans, RH 5 ans…) sont des valeurs FR par défaut, à valider/ajuster par juridiction (table `dim_domain_retention` éditable).
- **Âge = inactivité de la table**, pas âge réel de la donnée : une table active peut contenir des données hors durée légale (et inversement). Proxy à améliorer avec un vrai signal de date de transaction.
- **Signal de purge manquant** : les historiques de purge réels (MongoDB) ne sont pas encore intégrés.
