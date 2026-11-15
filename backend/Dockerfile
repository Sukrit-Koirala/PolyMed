FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY pytest.ini .
RUN useradd --create-home clinicalsync && chown -R clinicalsync:clinicalsync /app
USER clinicalsync
EXPOSE 8000
CMD ["sh", "backend/entrypoint.sh"]
