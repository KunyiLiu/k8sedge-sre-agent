# Use a pinned python version for stability
FROM python:3.11-slim

# 1. Install uv by copying it from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Set environment variables for optimization
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- NEW: Install kubelogin and its dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && curl -LO https://github.com/Azure/kubelogin/releases/download/v0.1.4/kubelogin-linux-amd64.zip \
    && unzip kubelogin-linux-amd64.zip -d ./kubelogin_dir \
    && mv ./kubelogin_dir/bin/linux_amd64/kubelogin /usr/local/bin/kubelogin \
    && rm -rf kubelogin-linux-amd64.zip ./kubelogin_dir \
    && apt-get purge -y --auto-remove unzip \
    && rm -rf /var/lib/apt/lists/*
# ---------------------------------------------------

# 3. Copy only dependency files first to leverage Docker caching
COPY pyproject.toml uv.lock ./

# 4. Create the virtual environment and install dependencies
RUN uv sync --frozen --no-dev

# 5. Copy the application code
COPY ./app ./app

# 6. Run the app using the virtual environment's path
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]