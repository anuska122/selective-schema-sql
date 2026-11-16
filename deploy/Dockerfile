FROM postgres:16-bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /usr/local/bin/uv

RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PGDATA=/home/user/pgdata \
    PGHOST=/tmp \
    UV_PYTHON_INSTALL_DIR=/home/user/python \
    UV_PROJECT_ENVIRONMENT=/home/user/venv \
    UV_CACHE_DIR=/home/user/.cache/uv \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed \
    SQLAGENT_PG_HOST=127.0.0.1 \
    SQLAGENT_PG_PORT=5432 \
    SQLAGENT_LIMIT_DB=/home/user/quota/limits.sqlite3

WORKDIR /home/user/app

COPY --chown=user pyproject.toml uv.lock ./
RUN uv python install 3.12 && uv sync --frozen --no-dev --no-install-project
COPY --chown=user src ./src
RUN uv sync --frozen --no-dev

COPY --chown=user eval/table_db_map.json ./eval/table_db_map.json
COPY --chown=user sql/00_roles.sql ./sql/00_roles.sql
COPY --chown=user data/index ./data/index
COPY --chown=user deploy/entrypoint.sh /home/user/entrypoint.sh

RUN uv run --frozen --no-dev python -c \
    "from sqlagent.index.embeddings import FastEmbedEmbedder; FastEmbedEmbedder().embed(['warm up'])"

COPY --chown=user bird.dump /home/user/bird.dump
RUN set -eux; \
    initdb -D "$PGDATA" -U user --auth-local=trust --auth-host=scram-sha-256; \
    pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -k /tmp" -w start; \
    createdb -U user bird; \
    pg_restore -U user -d bird --no-owner --no-privileges -j 4 /home/user/bird.dump; \
    psql -U user -q -d bird -v ON_ERROR_STOP=1 -v ro_password=bootstrap -f ./sql/00_roles.sql; \
    pg_ctl -D "$PGDATA" -m fast -w stop; \
    rm -f /home/user/bird.dump

RUN mkdir -p /home/user/quota

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
    CMD uv run --frozen --no-dev python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '7860') + '/ready', timeout=10).close()"
ENTRYPOINT ["/home/user/entrypoint.sh"]
