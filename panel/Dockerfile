FROM python:3.12-slim

LABEL maintainer="VodkinNET"
LABEL description="AWG-RT panel — management UI/API for AmneziaWG nodes and router fleet"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/

RUN useradd --create-home --shell /bin/false panel
RUN chown -R panel:panel /app
USER panel

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
