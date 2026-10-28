FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /opt/sqe
RUN apt-get update && apt-get install -y --no-install-recommends libglu1-mesa libgl1 libegl1 tini && rm -rf /var/lib/apt/lists/*
COPY . .
RUN python -m pip install --no-cache-dir -r requirements/core.lock && python -m pip install --no-cache-dir '.[web]'
RUN useradd --uid 10001 --create-home studio && mkdir -p /data && chown studio:studio /data
USER studio
ENV SQE_DATA=/data
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "--no-control-socket", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "300", "sqw.studio.server:create_app()"]
