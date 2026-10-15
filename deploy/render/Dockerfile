FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html frontend/tsconfig.json ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app
COPY --chown=user:user backend ./backend
RUN pip install --no-cache-dir -e './backend[postgres,pgvector]'
COPY --chown=user:user datasets/golden_scenarios.json ./datasets/golden_scenarios.json
COPY --chown=user:user docs ./docs
COPY --from=frontend --chown=user:user /build/frontend/dist ./frontend/dist
USER user
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn masguardeval.web:app --host 0.0.0.0 --port ${PORT:-10000}"]
