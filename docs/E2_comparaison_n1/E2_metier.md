# E2 — Comparaison N-1 : Fiche Métier

> **Statut :** ✅ Complet (réel, snapshots historiques) · **Devise :** USD

---

## Qu'est-ce qu'on fait dans cette section ?

On compare la situation **actuelle (N)** avec celle du **run précédent (N-1)** pour mesurer comment le patrimoine de données — et son coût — évolue dans le temps, **domaine par domaine**.

---

## La méthode : une vraie photo d'archive, pas une estimation

À chaque analyse de coût, le système enregistre une **photo** (un « snapshot ») du volume et du coût de chaque domaine. Quand un nouveau run arrive, on compare les **deux dernières photos réelles**.

> Avant, faute d'historique, on *reconstruisait* le passé en supposant +15 %/an. Maintenant, on compare **deux mesures réelles** : c'est factuel, vérifiable, et ça peut surprendre.

---

## Résultat réel — run 6 vs run 5

| | Volume N-1 (run 5) | Volume N (run 6) | Évolution |
|---|---|---|---|
| **Patrimoine total** | **11,76 Go** | **7,84 Go** | **−33 %** |
| IT & Sécurité | 6,07 Go | 6,69 Go | +10 % |
| Finance & Contrôle | 0,52 Go | 0,55 Go | +6 % |

**Ce que ça raconte honnêtement :** entre les deux extractions, le volume total mesuré a **baissé**. Ce n'est pas que les données disparaissent : les deux runs n'ont pas couvert exactement le même périmètre. Une comparaison réelle **montre la vérité brute** — y compris quand elle est moins flatteuse qu'une jolie courbe à +15 %.

---

## Pourquoi c'est important pour le PFE

C'est un **gage de sérieux** vis-à-vis du jury :

> « Nous ne maquillons pas les chiffres. La comparaison N-1 s'appuie sur des mesures réelles conservées par le pipeline. Quand l'historique n'est pas encore un signal fiable, nous le disons — et notre projection ROI en tient compte plutôt que d'extrapoler une fausse tendance. »

C'est exactement ce qui sépare une démo « vitrine » d'un outil de gouvernance crédible : **dès qu'un 3ᵉ, 4ᵉ run s'accumulera, la tendance se stabilisera toute seule**, sans changer une ligne de code.
