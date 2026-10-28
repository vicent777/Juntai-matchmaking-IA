
from fastapi import FastAPI

app = FastAPI(
    title="Juntai Matchmaking IA",
    description="API de recomendação de startups para investidores",
    version="0.1.0",
)


@app.get("/")
def home():
    return {
        "mensagem": "API de matchmaking funcionando!"
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
