#!/usr/bin/env python3
"""Gera site/dados_comercio.js a partir de config/dados.json.
A fonte da verdade é o JSON do repositório; numa fase futura, planilhas Google
entram aqui pelo mesmo caminho da Central TRX de laudos (conta de serviço)."""
import datetime as dt, json, os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = dt.timezone(dt.timedelta(hours=-3))

dados = json.load(open(os.path.join(RAIZ, "config", "dados.json"), encoding="utf-8"))
dados["gerado"] = dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")

# Radar de licitações pequenas de descartáveis (scripts/radar_comercio.py): o que ele
# gravou em data/radar.json entra na aba Licitações da página.
try:
    radar = json.load(open(os.path.join(RAIZ, "data", "radar.json"), encoding="utf-8"))
    dados["radar"] = {"gerado": radar.get("gerado", ""), "teto": radar.get("teto"),
                       "ufs": radar.get("ufs", []), "itens": radar.get("itens", [])}
except Exception:
    dados["radar"] = {"gerado": "", "itens": []}

# Mapa de plataformas de compras publicas (scripts/plataformas.py): o radar
# retroalimenta este arquivo a cada rodada e a pagina mostra o que ja esta
# mapeado e o que apareceu de novo e espera decisao do Marcos.
try:
    plat = json.load(open(os.path.join(RAIZ, "data", "plataformas.json"), encoding="utf-8"))
    dados["plataformas"] = {
        "gerado": plat.get("gerado", ""),
        "conhecidas": plat.get("conhecidas", []),
        "entes": plat.get("entes_regulamento_proprio", []),
        "novas": plat.get("novas", []),
        "estatistica": plat.get("estatistica", {}),
    }
except Exception:
    dados["plataformas"] = {"gerado": "", "conhecidas": [], "entes": [], "novas": [], "estatistica": {}}
js = "window.COMERCIO=" + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
open(os.path.join(RAIZ, "site", "dados_comercio.js"), "w", encoding="utf-8").write(js)
print(f"OK dados_comercio.js: {len(dados['documentos'])} documentos, gerado {dados['gerado']}")
