# 🎨 NeuroCarousel Bot

Телеграм-бот, который превращает любую тему в профессиональную нейрокарусель из 10 картинок.

```
Пользователь → тема → Gemini (сценарий 10 слайдов) → HF SDXL (10 картинок) → Telegram карусель
```

---

## 📁 Структура проекта

```
neurocarousel/
├── api/
│   └── bot.py                  # Vercel serverless webhook
├── bot/
│   ├── __init__.py
│   ├── neuro_carousel.py       # Публичный фасад
│   ├── config.py               # Настройки и константы
│   ├── models.py               # Slide, CarouselJob, VisualStyle
│   ├── texts.py                # Тексты для пользователя
│   ├── keyboards.py            # Inline-клавиатуры
│   ├── utils.py                # Валидация, JSON, сжатие изображений
│   ├── carousel.py             # Оркестрация генерации
│   ├── handlers/
│   │   └── updates.py          # Маршрутизация update → handlers
│   └── services/
│       ├── telegram.py         # Telegram Bot API
│       ├── gemini.py           # Генерация сценария
│       └── images.py           # HF SDXL + Pollinations
├── vercel.json
├── requirements.txt
├── .env.example
├── setup_webhook.py
└── README.md
```

---

## 🚀 Инструкция по деплою

### 1. Создание Telegram-бота

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Укажи имя: `NeuroCarousel`
4. Укажи username: `your_neurocarousel_bot`
5. Скопируй токен: `1234567890:ABCdef...`

---

### 2. Получение Gemini API Key (бесплатно)

1. Перейди на [aistudio.google.com](https://aistudio.google.com)
2. Нажми **"Get API Key"** → **"Create API Key"**
3. Скопируй ключ вида `AIza...`
4. Бесплатный тир: 15 RPM, 1 500 000 токенов/день — достаточно для бота

---

### 3. Получение Hugging Face API Key (бесплатно)

1. Зарегистрируйся на [huggingface.co](https://huggingface.co)
2. Перейди в [Settings → Access Tokens](https://huggingface.co/settings/tokens)
3. Нажми **"New token"** → тип **"Read"**
4. Скопируй токен вида `hf_...`
5. Бесплатный тир: ~720 CPU-часов/месяц, Rate limit ~1 req/sec

> ⚡ **Fallback**: если HF недоступен, бот автоматически использует
> [Pollinations.ai](https://pollinations.ai) — полностью бесплатный, без ключа.

---

### 4. Деплой на Vercel

#### Установка Vercel CLI
```bash
npm install -g vercel
vercel login
```

#### Клонирование и настройка
```bash
git clone https://github.com/your/neurocarousel.git
cd neurocarousel

# Добавляем переменные окружения в Vercel
vercel env add TELEGRAM_TOKEN
# → вставляешь токен бота

vercel env add GEMINI_API_KEY
# → вставляешь Gemini ключ

vercel env add HF_API_KEY
# → вставляешь HF токен
```

#### Деплой
```bash
vercel --prod
```

После деплоя ты увидишь URL вида:
```
✅  Production: https://neurocarousel-xxxx.vercel.app
```

---

### 5. Регистрация Webhook

```bash
TELEGRAM_TOKEN=your_token VERCEL_URL=https://neurocarousel-xxxx.vercel.app python setup_webhook.py
```

Или вручную через curl:
```bash
curl -X POST "https://api.telegram.org/botYOUR_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://neurocarousel-xxxx.vercel.app/api/bot", "drop_pending_updates": true}'
```

---

### 6. Проверка

Открой бота в Telegram и отправь `/start`.
Должно прийти приветствие. Затем напиши тему:

```
Утренние ритуалы успешных людей
```

Через 1–3 минуты придёт карусель из 10 картинок 🎉

---

## ⚙️ Технические решения

| Компонент | Решение | Причина |
|-----------|---------|---------|
| Архитектура | Слои: handlers → carousel → services | Разделение ответственности, проще расширять |
| Webhook runtime | Vercel Python Serverless | Бесплатный хостинг, авто-масштабирование |
| Сценарий | Google Gemini 2.0 Flash | Быстрый, бесплатный, JSON-режим |
| Изображения | HF SDXL Base 1.0 | Лучшее качество в бесплатном тире |
| Fallback | Pollinations.ai | Без ключа, надёжный |
| HTTP клиент | httpx async | Современный, поддержка multipart |
| Сжатие | Pillow JPEG | Быстрее отправка в Telegram |
| UX | Inline-клавиатуры, 5 стилей | Выбор стиля и примеров без ввода |
| Rate limiting | Последовательная генерация + sleep | Соблюдение лимитов HF Free Tier |
| Кэш | По chat+topic+style | Безопасный retry без смешивания тем |
| Блокировка | JobRegistry per chat | Защита от параллельных запросов |

### Почему последовательная генерация, а не параллельная?

HF Inference API в бесплатном тире ограничен ~1 запросом в секунду.
Параллельные запросы вызовут массовые 429. Между запросами — пауза 2.5 сек.
Итого ~30 сек на 10 слайдов — приемлемо для пользователя.

### Timeout Vercel

Vercel Pro/Hobby позволяет до 300 секунд для serverless функций.
В `vercel.json` выставлено `"maxDuration": 300`.

---

## 🔧 Локальная разработка

```bash
pip install httpx pillow python-dotenv
cp .env.example .env
# Заполни .env

# Запуск локального сервера (ngrok для webhook)
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

# Для теста можно вызвать handle_update напрямую
from bot.neuro_carousel import NeuroCarouselBot
import asyncio

bot = NeuroCarouselBot(
    token=os.environ['TELEGRAM_TOKEN'],
    gemini_key=os.environ['GEMINI_API_KEY'],
    hf_key=os.environ['HF_API_KEY'],
)

# Тест с фейковым update
asyncio.run(bot.handle_update({
    'message': {
        'chat': {'id': 123456789},
        'text': 'Японская эстетика ваби-саби'
    }
}))
"
```

---

## 📊 Лимиты бесплатных тиров

| Сервис | Лимит | Хватит ли? |
|--------|-------|------------|
| Gemini 2.0 Flash | 15 RPM, 1.5M токенов/день | ✅ С запасом |
| HF Inference | ~720 CPU-ч/месяц, 1 req/s | ✅ ~2000 каруселей |
| Pollinations.ai | Без лимитов | ✅ Fallback |
| Vercel Hobby | 100GB bandwidth, 100h compute | ✅ Для старта |

---

## 🐛 Troubleshooting

**Бот не отвечает**
```bash
# Проверь webhook статус
curl "https://api.telegram.org/botYOUR_TOKEN/getWebhookInfo"
```

**HF возвращает 503**
Модель "засыпает" в бесплатном тире. Первый запрос может занять 20-40 сек на прогрев.
Бот автоматически ретраит 3 раза. Если всё равно не получается — используется Pollinations.

**Vercel timeout**
Если генерация 10 картинок занимает >300 сек, уменьши `num_inference_steps` в `bot/services/images.py`:
```python
"num_inference_steps": 20,  # Было 28
```

**Кнопки не работают**
Перерегистрируй webhook с `callback_query`:
```bash
python setup_webhook.py
```
