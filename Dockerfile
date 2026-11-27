FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 recallguard
WORKDIR /opt/recallguard
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
RUN pip install --no-cache-dir --no-deps .
COPY dashboard ./dashboard
COPY ["data/recalls_recall_listing (1).csv", "./data/"]
COPY .streamlit ./.streamlit
COPY results/metrics/*.json ./results/metrics/
USER recallguard
EXPOSE 8000 8501
CMD ["uvicorn", "recallguard.api:app", "--host", "0.0.0.0"]
