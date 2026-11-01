FROM python:3.12-slim
WORKDIR /srv/hub
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends clamav tesseract-ocr ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m hub
COPY app app
COPY config config
COPY scripts scripts
RUN mkdir -p data && chown -R hub:hub /srv/hub
USER hub
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=3)"
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8001","--workers","1"]
