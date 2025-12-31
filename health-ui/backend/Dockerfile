# Use a pinned python version for stability
FROM python:3.11-slim

# 1. Install uv by copying it from the official image (fastest & cleanest)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Set environment variables for optimization
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 3. Copy only dependency files first to leverage Docker caching
# (This ensures 'uv sync' only runs if your dependencies change)
COPY pyproject.toml uv.lock ./

# 4. Create the virtual environment and install dependencies
# --frozen ensures we use the exact versions in the lockfile
RUN uv sync --frozen --no-dev

# 5. Copy the application code
COPY ./app ./app

# 6. Run the app using the virtual environment's path
# This avoids needing to "activate" the environment manually
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]