# TripVote ✈️

Application web collaborative pour choisir en groupe la destination d'un weekend.

- **Présentation** : https://potatoesfra.github.io/demo_selection_voyage/
- **Démo** : https://demo-selection-voyage.onrender.com (le plan gratuit de Render peut mettre 30 à 60 s à démarrer)

## Fonctionnalités

- **Admin** : crée le voyage, ajoute les participants et les propositions (galerie photo, prix par personne, pour et contre, adresse, lien vers l'annonce)
- **Participants** : entrent sans compte (prénom + emoji), reconnexion automatique par cookie pendant 30 jours, détection des profils au nom similaire
- **Votes** : chacun aime autant de propositions qu'il veut
- **Droit de véto** : un seul « NON » par participant, déplaçable ou retirable
- **Carte interactive** : Leaflet + OpenStreetMap, adresses géocodées avec Nominatim
- **Temps de trajet** : durée en voiture depuis Paris, Marseille, Bordeaux et Toulouse (OSRM) et gare la plus proche
- **Résultats en temps réel** : rafraîchis automatiquement toutes les 5 secondes

## Lancer en local

```bash
pip install -r requirements.txt
export DATABASE_URL=sqlite:///tripvote.db
export SECRET_KEY=une-cle-secrete
export ADMIN_PASSWORD=mot-de-passe-admin
python app.py
```

L'app est accessible sur http://localhost:5000

## Déployer sur Render (gratuit)

1. Créez une base PostgreSQL externe (ex. Neon) : le disque de Render est effacé à chaque redémarrage
2. Sur [render.com](https://render.com) → New → Blueprint, connectez ce dépôt : `render.yaml` décrit le service
3. Renseignez `ADMIN_PASSWORD` et `DATABASE_URL` (`SECRET_KEY` est générée par Render)
4. Déployez

## Variables d'environnement

Toutes sont obligatoires, il n'y a pas de valeur par défaut.

| Variable | Description |
|---|---|
| `DATABASE_URL` | URL SQLAlchemy de la base (`postgres://` est converti en `postgresql://`) |
| `SECRET_KEY` | Clé secrète Flask (sessions) |
| `ADMIN_PASSWORD` | Mot de passe de l'espace admin |

## Structure

```
├── app.py              # Flask : modèles, routes, API
├── requirements.txt
├── Procfile            # Commande de démarrage (gunicorn)
├── render.yaml         # Service Render
├── docs/               # Page de présentation (GitHub Pages)
└── templates/
    ├── base.html       # Layout commun
    ├── index.html      # Accueil : choix ou création du profil
    ├── trip.html       # Vue principale (propositions, résultats, carte)
    ├── admin.html      # Tableau de bord admin
    └── admin_login.html
```

## Workflow

1. **Admin** → `/admin/login` → crée le voyage → ajoute participants et propositions
2. **Participants** → `/` → choisissent ou créent leur profil → votent sur `/trip`
3. Tout le monde voit les résultats en temps réel dans l'onglet « Résultats »
