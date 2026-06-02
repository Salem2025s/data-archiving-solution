# E2 — Comparaison N-1 : Fiche Métier

> **Statut :** ✅ Complet (par simulation) · **Devise :** USD

---

## Qu'est-ce qu'on fait dans cette section ?

On compare la situation **actuelle (N)** avec celle d'**il y a un an (N-1)** pour mesurer la croissance des données et son coût.

---

## La méthode

On ne dispose que d'un seul instantané de la base. On reconstruit donc le passé mathématiquement : si la base croît de 15 %/an, l'an dernier elle était plus petite de 15 %.

```
Patrimoine N-1 = Patrimoine actuel ÷ 1,15
```

---

## Résultat run_id=5

| | Volume | Coût annuel |
|---|---|---|
| N-1 (il y a 1 an, simulé) | 6,81 Go | 1,88 $/an |
| N (aujourd'hui) | 7,84 Go | 2,16 $/an |
| **Croissance** | **+1,02 Go** | **+0,28 $/an** |

En un an, la base a gagné ~1 Go et son coût a augmenté de 0,28 $/an. À ce rythme, **sans archivage le coût croît de 15 % chaque année**.

---

## Pourquoi c'est utile ?

Cette comparaison montre une **dynamique**, pas juste une photo :

> « Le patrimoine grossit de 15 %/an. Sans rien faire, le coût double tous les ~5 ans. L'archivage permet de casser cette courbe. »

---

## Évolution prévue

Aujourd'hui la comparaison est **simulée** (un seul snapshot). Dès qu'une deuxième extraction Oracle sera lancée (run_id=6), la comparaison deviendra **réelle et factuelle** — le pipeline conserve l'historique de tous les runs.
