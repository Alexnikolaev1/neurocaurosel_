"""Проверка деплоя: GET https://YOUR_DOMAIN.vercel.app/api/health"""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI()


@app.get("/")
async def health() -> PlainTextResponse:
    return PlainTextResponse("API functions work on Vercel")
