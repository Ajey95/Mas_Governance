FROM python:3.12-slim
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app
COPY --chown=user:user backend ./backend
RUN pip install --no-cache-dir -e ./backend
COPY --chown=user:user website ./website
USER user
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn masguardeval.official_site:app --host 0.0.0.0 --port ${PORT:-10000}"]
