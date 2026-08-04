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

COPY . /code

# Ensure runtime dirs exist (uploads/static writable for HF UID 1000)
RUN mkdir -p /code/uploads /code/static /code/data/villages \
    && chmod -R 777 /code

EXPOSE 7860

CMD ["gunicorn", "-b", "0.0.0.0:7860", "--workers", "1", "--threads", "4", "--timeout", "600", "app:app"]
