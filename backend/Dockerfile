# Development image for the Django API, used by docker-compose.yml.
# (Production runs straight on the VPS under systemd + gunicorn, see deploy/.)
FROM python:3.13-slim

# mysqlclient is a C extension: building it needs a compiler and the MySQL client headers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Copy only requirements first: this layer is cached, so code changes don't reinstall every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Print logs immediately instead of buffering them (otherwise `docker compose logs` lags behind).
ENV PYTHONUNBUFFERED=1

# The code itself is bind-mounted by docker-compose, so edits reload without rebuilding the image.
