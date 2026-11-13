#!/usr/bin/env python3
"""Radar PNCP da TRX Comércio: procura, todo dia, licitações PEQUENAS de produtos
descartáveis hospitalares e grava o resultado em data/radar.json, que a página da
Central Comércio mostra na aba Licitações (mesmo espírito do radar de telelaudo
da Central TRX de laudos).

Regras desta primeira fase (12/11/2026, a refinar com o uso):
- Só volumes pequenos: valor global até TETO (padrão R$ 60.000, na faixa de
  dispensa), porque o fluxo de caixa da TRX Comércio ainda é pequeno.
- Só DF e GO por padrão (entrega física; frete pesa), ajustável em UFS.
- Descartáveis e insumos; medicamentos, equipamentos, serviços e obras ficam fora.

Sem segredos: a API do PNCP é pública. O estado (IDs já vistos) fica em
data/radar_vistos.json para a lista não zerar entre rodadas.
"""
import datetime as dt, json, os, re, time, unicodedata, urllib.parse, urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
TZ = dt.timezone(dt.timedelta(hours=-3))
URL = "https://pncp.gov.br/api/search/"

TETO = float(os.environ.get("RADAR_TETO", "60000"))
UFS = [u.strip().upper() for u in os.environ.get("RADAR_UFS", "DF,GO").split(",") if u.strip()]
DIAS_GUARDA = 45   # itens com prazo vencido há mais que isso saem da lista

# A busca do PNCP exige TODAS as palavras do termo: termos curtos.
TERMOS = ["material hospitalar descartavel", "material medico hospitalar", "luvas de procedimento",
          "luvas descartaveis", "seringas agulhas", "gaze atadura", "compressa de gaze",
          "mascara descartavel", "avental descartavel", "esparadrapo", "algodao hidrofilo",
          "touca descartavel", "papel grau cirurgico", "curativos", "equipo macrogotas",
          "material odontologico", "insumos odontologicos", "material de enfermagem",
          "soro fisiologico", "cateter sonda"]

# Tem de falar de material/insumo descartável ou hospitalar.
DENTRO = ["descartav", "hospitalar", "luva", "seringa", "agulha", "gaze", "atadura", "compressa",
          "mascara", "avental", "esparadrapo", "algodao", "touca", "grau cirurgico", "curativo",
          "equipo", "cateter", "sonda", "enfermagem", "odontolog", "soro", "insumo", "scalp",
          "abaixador", "termometro", "coletor", "fralda", "lencol", "campo operatorio"]

# Fora do perfil: serviço, obra, equipamento permanente, medicamento, alimento, limpeza pesada.
FORA = ["medicament", "farmac", "obra", "reforma", "engenharia", "pavimenta", "locacao", "comodato",
        "manutencao", "prestacao de servico", "servicos de", "laudo", "radiolog", "telemedicina",
        "consulta", "plantao", "mao de obra", "software", "equipament", "aparelho", "autoclave",
        "cadeira odontologica", "compressor", "ultrassom", "raio-x", "raio x", "tomograf",
        "generos aliment", "merenda", "combustivel", "uniforme", "mobiliario", "informatica",
        "toner", "papelaria", "expediente", "veicul", "pneu", "grafic", "vale", "seguro",
        "limpeza predial", "vigilancia", "dedetiza", "lavanderia", "coffee", "evento",
        "oxigenio", "gases medicinais", "protese", "ortese", "implante"]


def sem_acento(t):
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def buscar(termo):
    itens, pagina = [], 1
    # 1 página por termo, ordenada por -data: a rodada é diária e incremental, não precisa varrer fundo.
    while pagina <= 1:
        q = urllib.parse.urlencode({"tipos_documento": "edital", "status": "recebendo_proposta",
                                    "q": termo, "tam_pagina": 100, "pagina": pagina,
                                    "ordenacao": "-data"})
        req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "central-trx-comercio/1.0",
                                                           "Accept": "application/json"})
        doc = None
        for tentativa in range(2):
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    doc = json.load(r)
                break
            except Exception:
                if tentativa == 1:
                    raise
                time.sleep(5 * (tentativa + 1) ** 2)
        lote = doc.get("items") or []
        itens += lote
        if len(lote) < 100:
            break
        pagina += 1
        time.sleep(1)
    return itens


def relevante(it):
    """(entra?, motivo) pela régua da primeira fase.

    O motivo começa com "uf:" ou "teto:" quando o OBJETO é do perfil e só a
    geografia ou a escala reprovaram. Esses dois casos não entram no radar, mas
    servem para descobrir plataformas (scripts/plataformas.py): o edital é de
    material hospitalar e revela em que sistema a disputa acontece.
    """
    texto = sem_acento((it.get("description") or "") + " " + (it.get("title") or ""))
    if not any(p in texto for p in DENTRO):
        return False, "sem material do perfil no objeto"
    for p in FORA:
        if p in texto:
            return False, f"fora do perfil ({p.strip()})"
    uf = str(it.get("uf") or "").upper()
    if UFS and uf not in UFS:
        return False, f"uf: fora das UFs ({uf or '?'})"
    valor = it.get("valor_global")
    if isinstance(valor, (int, float)) and valor > TETO:
        return False, f"teto: acima do teto (R$ {valor:,.0f})"
    return True, ""


def data_iso(v):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v or ""))
    return m.group(0) if m else ""


def item_de(it, agora):
    cnpj = str(it.get("orgao_cnpj") or "")
    ano, seq = it.get("ano"), it.get("numero_sequencial")
    link = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}" if cnpj and ano and seq else ""
    valor = it.get("valor_global")
    return {
        "id": str(it.get("numero_controle_pncp") or "").strip(),
        "orgao": it.get("orgao_nome") or "",
        "cidade": it.get("municipio_nome") or "",
        "uf": it.get("uf") or "",
        "modalidade": it.get("modalidade_licitacao_nome") or "",
        "edital": it.get("title") or "",
        "objeto": (it.get("description") or "")[:600],
        "valor": valor if isinstance(valor, (int, float)) and valor > 0 else None,
        "prazo": data_iso(it.get("data_fim_vigencia")),
        "link": link,
        "visto_em": agora,
    }


def main():
    os.makedirs(DATA, exist_ok=True)
    agora = dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    hoje = agora[:10]

    try:
        atual = json.load(open(os.path.join(DATA, "radar.json"), encoding="utf-8"))
    except Exception:
        atual = {"itens": []}
    por_id = {i["id"]: i for i in atual.get("itens", []) if i.get("id")}

    achados, descartes = {}, 0
    # Itens de material hospitalar vistos nesta rodada, inclusive os que ficaram
    # fora do radar só por UF ou por teto: alimentam a descoberta de plataformas.
    perfil = {}
    for termo in TERMOS:
        try:
            lote = buscar(termo)
        except Exception as e:
            print(f"::warning::busca '{termo}' falhou: {e}")
            continue
        for it in lote:
            pid = str(it.get("numero_controle_pncp") or "").strip()
            if not pid or pid in achados:
                continue
            ok, motivo = relevante(it)
            if ok or motivo.startswith(("uf:", "teto:")):
                perfil.setdefault(pid, it)
            if not ok:
                descartes += 1
                continue
            achados[pid] = item_de(it, agora)
        time.sleep(1)

    novos = 0
    for pid, item in achados.items():
        if pid in por_id:
            por_id[pid].update({k: v for k, v in item.items() if k != "visto_em"})
        else:
            item["novo_em"] = hoje
            por_id[pid] = item
            novos += 1

    # poda: prazo vencido há mais de DIAS_GUARDA dias sai da lista
    limite = (dt.datetime.now(TZ) - dt.timedelta(days=DIAS_GUARDA)).strftime("%Y-%m-%d")
    itens = [i for i in por_id.values() if not i.get("prazo") or i["prazo"] >= limite]
    itens.sort(key=lambda i: (i.get("prazo") or "9999", -(i.get("valor") or 0)))

    saida = {"gerado": agora, "teto": TETO, "ufs": UFS, "itens": itens}
    json.dump(saida, open(os.path.join(DATA, "radar.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"OK radar: {len(itens)} na lista ({novos} novos hoje), {descartes} descartados no filtro")

    # Mesma rodada, segunda entrega: cada edital de material hospitalar diz em que
    # plataforma a disputa acontece. Dominio novo vira linha para o Marcos decidir.
    # Falha aqui nao derruba o radar: a lista de licitacoes e o produto principal.
    try:
        import plataformas
        plataformas.retroalimentar(list(perfil.values()), hoje=hoje)
    except Exception as e:
        print(f"::warning::retroalimentacao de plataformas falhou: {e}")


if __name__ == "__main__":
    main()
