FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc pkg-config default-libmysqlclient-dev curl \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 3000
CMD ["sh", "-c", "gunicorn app:application -b 0.0.0.0:3000 -w ${WEB_CONCURRENCY:-1} --threads ${PY_THREADS:-1} --worker-class ${PY_WORKER_CLASS:-gthread} --log-level warning --access-logfile /dev/null"]
