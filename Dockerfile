# `python-base` sets up all our shared environment variables
FROM python:3.12-slim AS python-poetry-build-base

    # python no pyc files + pip longer timeout
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # poetry set location
    POETRY_VERSION=2.1.2 \
    POETRY_HOME="/opt/poetry" \
    \
    # Poetry can create a venv for you, but it will be a random venv name 
    # You could also have POETRY_VIRTUALENVS_IN_PROJECT=1 to get a deterministic venv name
    # but it will be in the project directory, which might cause problem if you wanna mount your project in dev
    # Instead we create/activate our own venv in a known location, prompting poetry to use it
    # Once poetry lets us set the venv name in its confing, we can remove this 
    # Ref: https://github.com/python-poetry/poetry/issues/263#issuecomment-1404129650
    VIRTUAL_ENV="/opt/pysetup/venv"

# create the venv and activate it
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# install poetry 
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        curl \
        build-essential
# use official curl to respect $POETRY_VERSION & $POETRY_HOME
# (pip install poetry doesn't respect $POETRY_HOME)
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

# builder-base installs shared deps (dev + prod), but not the root package.
# We skip root package here to control how/when it's installed later (editable vs wheel),
# and to avoid copying source code into this stage.
FROM python-poetry-build-base AS builder-base

# install the common deps, filter the group you want
COPY poetry.lock pyproject.toml ./
RUN poetry install --without dev --no-root


# `development` image is used during development
FROM python-poetry-build-base AS development

# copy in our poetry and base built venv
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $VIRTUAL_ENV $VIRTUAL_ENV
WORKDIR /app
# copy image-specific deps, filter the group you want
COPY --from=builder-base poetry.lock pyproject.toml ./
RUN poetry install --only dev --no-root
# Install root package in editable mode (default for Poetry)
# Dummy README to satisfy Poetry
# Use touch to avoid cache busting on real README changes
RUN touch README.md
COPY src/ src/
RUN poetry install --only-root
COPY . .

CMD [ "poetry", "run", "oidfed-collector" ]


# `production` intermediate building image
FROM python-poetry-build-base AS production-builder
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $VIRTUAL_ENV $VIRTUAL_ENV

WORKDIR /temp
# copy production-specific deps, filter the group you want
COPY --from=builder-base pyproject.toml ./
# Dummy README to satisfy Poetry
# Use touch to avoid cache busting on real README changes
RUN touch README.md
COPY src/ src/
# Use wheel + pip to avoid editable install (default in Poetry)
# If editable install, you'd need to recopy the source in the final prod image, better to just reuse the venv
RUN poetry build && pip install dist/*.whl



# `production` image used for runtime
# Use clean python-slim image to reduce size, we don't need the other ENV vars or poetry
FROM python:3.12-slim AS production

ENV VIRTUAL_ENV="/opt/pysetup/venv"
COPY --from=production-builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
CMD ["oidfed-collector"]
