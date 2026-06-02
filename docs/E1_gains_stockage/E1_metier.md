# E1 — Gains de stockage et coût avant/après : Fiche Métier

> **Statut :** ✅ Complet · **Devise :** USD

---

## Qu'est-ce qu'on fait dans cette section ?

On traduit les volumes de données en **impact financier** : combien coûte le stockage aujourd'hui, et combien on économise en archivant.

---

## Le modèle de coût (tarifs cloud réels AWS)

| Type de stockage | Coût | Service |
|---|---|---|
| Actif | 0,276 $/Go/an | AWS S3 Standard |
| Froid (archive) | 0,048 $/Go/an | AWS Glacier Deep Archive |

Archiver une donnée la fait passer de 0,276 à 0,048 $/Go/an → **économie de 0,228 $/Go/an**, soit **233 $ par To archivé et par an**.

---

## Résultat run_id=5

| Indicateur | Valeur |
|---|---|
| Patrimoine analysé | 7,8 Go |
| Volume archivable | 7,7 Go (98 %) |
| Coût actuel | 2,16 $/an |
| Coût après archivage | 0,43 $/an |
| **Économie** | **1,73 $/an (−80 %)** |

---

## Pourquoi des montants si petits ?

L'instance Oracle analysée (EP92U038) est une **base de démonstration** : seulement ~8 Go de données physiques réelles (90 % des objets sont des structures logiques vides).

**Ce qui compte, c'est la méthode et le taux**, pas le montant absolu sur la démo :

> **233 $ économisés par To archivé et par an.**

Cette métrique se transpose directement à la production :

| Volume archivable en production | Économie annuelle estimée |
|---|---|
| 1 To | 233 $/an |
| 10 To | 2 335 $/an |
| 100 To | 23 347 $/an |

---

## Ce que ça apporte au PFE

- Donne une **valeur économique chiffrée** au projet d'archivage
- Montre une **réduction de coût de 80 %** sur le périmètre archivable
- Fournit un **taux unitaire transposable** à n'importe quelle volumétrie production
- Repose sur des **tarifs cloud publics et vérifiables** (AWS)
