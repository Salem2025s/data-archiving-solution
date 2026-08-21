# Image de déploiement de la solution de gouvernance (dashboard + pipeline).
# Modèle de production léger (LinearSVC, quelques Mo) — pas d'exigence GPU.
FROM python:3.13-slim

# Dépendances système minimales (psycopg / oracledb en mode thin : rien de natif requis)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Dépendances (couche cache séparée du code)
COPY requirements.txt requirements-ml.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install -r requirements-ml.txt

# 2) Code applicatif
COPY src/ ./src/
COPY app/ ./app/
COPY sql/ ./sql/
COPY artifacts/ ./artifacts/
COPY pyproject.toml ./

# 3) Utilisateur non-root (bonne pratique sécurité)
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Le dashboard Streamlit (les secrets et la connexion DB viennent de l'environnement)
EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_dashboard.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
