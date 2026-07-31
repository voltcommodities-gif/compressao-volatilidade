# Screening de Compressão de Volatilidade (Bollinger Squeeze)

Ferramenta de **estudo** que detecta o padrão clássico de **compressão de
volatilidade** — quando as **Bandas de Bollinger (20, 2σ)** se apertam para
**dentro dos Canais de Keltner (20, 1,5×ATR)** — e o **disparo** (a "mola"
soltando) quando as bandas voltam a se expandir. Painel web (GitHub Pages) no
mesmo formato dos outros screenings, com backtest de poder preditivo.

> ⚠️ **Ferramenta de estudo**, não é recomendação de investimento.

## Como funciona

- **Comprimido (squeeze on):** Bollinger inteiramente dentro do Keltner → baixa
  volatilidade, "mola comprimida".
- **Disparo:** o dia em que a compressão acaba (bandas saem do Keltner). A
  direção (▲ alta / ▼ baixa) vem do preço vs. a média (SMA20) no disparo.
- **Largura de banda:** (banda sup. − inf.) ÷ média, em %. Percentil na janela de
  ~6 meses mede o quão comprimida está a volatilidade.

Sem look-ahead: tudo usa janelas móveis (fecham no dia t com dados até t); o
disparo em t é conhecido no fechamento de t.

## Poder preditivo (backtest)

Para cada disparo, mede o retorno futuro em 10/20/40 candles na direção prevista,
o **edge** vs. a base (retorno incondicional do universo) e se a volatilidade de
fato **expandiu**. Achado honesto: **a compressão prevê muito bem a expansão de
volatilidade (~85% dos disparos), mas a direção tem pouco edge** — o squeeze avisa
que *vem um movimento grande*, não pra que lado. (Ajuste "mín. dias comprimido" e
o horizonte na UI.)

## Estrutura

```
compressao-volatilidade/
├── pipeline/  data.py · indicators.py · main.py
├── templates/painel.template.html
├── docs/index.html   (painel publicado)
└── tickers.txt · requirements.txt
```

## Rodar / publicar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline/main.py        # baixa, detecta e regrava docs/index.html
```

GitHub Pages: **Settings → Pages → branch `main`, pasta `/docs`.**
