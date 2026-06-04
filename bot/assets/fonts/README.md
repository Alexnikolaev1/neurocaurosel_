# Шрифты для режима «Текст на слайде»

В репозитории должен лежать **`NotoSans-Bold.ttf`** (кириллица + латиница).

Если файла нет, скачай:

```bash
curl -fsSL -o bot/assets/fonts/NotoSans-Bold.ttf \
  "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
```

Без этого файла на Vercel текст на слайде не отображается (только «квадратики»).
