FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
WORKDIR /app
RUN groupadd --gid 10001 radar && useradd --uid 10001 --gid radar radar && mkdir /data && chown radar:radar /data
COPY --chown=radar:radar app.py catalog.py dossier.py sources.json ./
COPY --chown=radar:radar public ./public
USER radar
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"
CMD ["python", "app.py"]
