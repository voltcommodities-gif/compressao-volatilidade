# Screening VCP — Volatility Contraction Pattern (Minervini)

Ferramenta de **estudo** que detecta o **VCP (Volatility Contraction Pattern)** de
Mark Minervini: uma **base** dentro de uma tendência de alta (Stage 2), formada por
**correções cada vez menores** (contrações que apertam), com **fundos ascendentes** e
**volume secando**, terminando num **ponto de pivô** (compra no rompimento). Painel
web (GitHub Pages) com backtest de poder preditivo.

> ⚠️ **Ferramenta de estudo**, não é recomendação de investimento.

## Regras do padrão (Minervini)

- **Tendência (Stage 2):** preço > MM50 > MM150 > MM200, todas subindo; perto da
  máxima de 52 semanas (≥30% acima da mínima, ≤25% abaixo da máxima).
- **Contrações:** série de correções, cada uma **menor que a anterior** (~metade),
  com **fundos ascendentes**. Tipicamente 3–4 (2 em mercado forte); a última bem
  apertada (3–8%).
- **Volume:** seca durante os recuos; **estoura ≥1,5× a média** no rompimento.
- **Pivô = topo da última contração.** Compra no rompimento; **stop 7–8%** abaixo.
  Alvo ≈ altura da base projetada a partir do pivô.

Sem look-ahead: topos/fundos só confirmam `order` (8) pregões depois; o rompimento
só é considerado a partir do pivô confirmado.

## O painel

- **Screening:** ativos com base VCP **em formação** (perto do pivô) ou **rompida**,
  com as contrações, distância ao pivô e Stage 2 — ordenável, clicável.
- **Por ativo:** preço + MM50/150/200, os pontos das contrações, a linha do pivô e
  os rompimentos; subgráfico de volume; e a tabela de todas as bases VCP com o
  retorno depois do rompimento (5–60 dias úteis).
- **Poder preditivo:** retorno médio, acerto, **edge vs. base** e taxa de "alvo antes
  do stop" dos rompimentos. (O VCP é feito para ações líderes de forte momentum — num
  universo genérico o edge é modesto.)
- **Metodologia:** aba explicando tudo.

## Estrutura

```
pipeline/  data.py · indicators.py (MAs, Stage 2) · vcp.py (detector) · main.py
templates/painel.template.html · docs/index.html · tickers.txt · requirements.txt
```

## Rodar / publicar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline/main.py        # baixa, detecta e regrava docs/index.html
```
GitHub Pages: **Settings → Pages → branch `main`, pasta `/docs`.**
