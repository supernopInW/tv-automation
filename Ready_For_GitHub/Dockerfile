FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HEADLESS=1 \
    FLASK_DEBUG=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /code

COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

RUN playwright install chromium

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && mkdir -p /tmp/tv-automation-uploads \
    && chown -R appuser:appuser /tmp/tv-automation-uploads

COPY --chown=appuser:appuser . /code
USER appuser

EXPOSE 7860

CMD ["gunicorn", "-b", "0.0.0.0:7860", "--workers", "1", "--threads", "4", "--timeout", "600", "app:app"]
