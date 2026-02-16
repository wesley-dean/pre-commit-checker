FROM python:3.15.0a6-slim

ENV RUNNER="runner"
ENV WORKDIR="/workdir/"

RUN mkdir -p "${WORKDIR}"

# Needed because pip will compile some deps (e.g., cffi) on Python 3.15 alpha
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc \
      build-essential \
      libffi-dev \
      python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR "${WORKDIR}"
COPY requirements.txt "${WORKDIR}"
RUN ( getent passwd "${RUNNER}" || adduser --disabled-password --gecos "" "${RUNNER}" ) \
&& pip install --no-cache-dir -r "${WORKDIR}requirements.txt"

HEALTHCHECK NONE

USER "${RUNNER}"
ENTRYPOINT ["python", "./pre_commit_checker.py"]
COPY pre_commit_checker.py templates/ "${WORKDIR}"/
