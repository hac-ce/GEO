FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home geo \
    && mkdir /data && chown geo:geo /data
ARG INSTALL_BROWSER=false
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN if [ "$INSTALL_BROWSER" = "true" ]; then python -m playwright install --with-deps chromium; fi
COPY backend/ ./backend/
USER geo
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=3)"
CMD ["python", "-m", "backend.app.container_entry"]
