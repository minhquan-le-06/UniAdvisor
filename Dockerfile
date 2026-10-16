# One container: the built web frontend and the API, for any Docker host (a Hugging Face Space, Render...; port 7860).
# The database is NOT in the image: at startup the API downloads it from a private dataset (src/uniadvisor/api/dbfetch.py)
# with the secrets HF_TOKEN and UNIADVISOR_DB_REPO set on the host. (Vercel does not use this file: see vercel.json.)

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 UNIADVISOR_DB_DIR=/tmp
RUN useradd -m -u 1000 user
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY models ./models
# Editable on purpose: the code finds config/ and models/ next to src/ (paths.py).
RUN pip install -e .
COPY --from=web /web/dist ./web/dist
RUN chown -R user:user /app
USER user
EXPOSE 7860
CMD ["uvicorn", "uniadvisor.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]
