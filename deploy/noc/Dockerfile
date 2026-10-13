FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
WORKDIR /src
COPY pyproject.toml uv.lock .python-version ./
COPY shared shared
COPY sentinel sentinel
COPY noc noc
RUN uv sync --frozen --no-dev --package noc --no-editable

FROM python:3.12-slim
RUN useradd --system --uid 10001 noc \
    && install -d -o noc -g noc /var/lib/noc/prometheus-targets
COPY --from=build /opt/venv /opt/venv
COPY --from=frontend /frontend/dist /opt/noc-frontend
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 NOC_FRONTEND_DIST=/opt/noc-frontend
USER noc
WORKDIR /home/noc
CMD ["noc", "--help"]
