FROM python:3.12-slim
WORKDIR /app
COPY outage_gap ./outage_gap
COPY api ./api
RUN pip install --no-cache-dir fastapi uvicorn pydantic pandas python-multipart
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
