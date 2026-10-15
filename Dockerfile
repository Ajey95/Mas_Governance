FROM python:3.12-slim
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app
COPY --chown=user:user backend ./backend
RUN pip install --no-cache-dir -e ./backend
COPY --chown=user:user website ./website
COPY --chown=user:user docs/README.md docs/QUICKSTART.md docs/SDK.md docs/SDK_PUBLIC_API.md docs/INTEGRATIONS.md docs/API.md docs/EXAMPLES.md docs/ARCHITECTURE.md docs/METRICS.md docs/EXPERIMENTS.md docs/RESEARCH_STATUS.md docs/STUDY_AUTHORING_GUIDE.md docs/PAPER_STUDY_PROTOCOL.md docs/RELATED_WORK_AUDIT.md ./docs/
USER user
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn masguardeval.official_site:app --host 0.0.0.0 --port ${PORT:-10000}"]
