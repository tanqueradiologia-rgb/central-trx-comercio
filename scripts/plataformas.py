#!/usr/bin/env python3
"""Descoberta de plataformas de compras publicas, acoplada ao radar da TRX Comercio.

Por que existe: o PNCP e so divulgacao. Quem recebe a proposta e o lance e outro
sistema, que o edital indica. O PNCP guarda esse endereco no registro da
contratacao, entao cada edital que o radar acha revela, de graca, em que
plataforma a TRX Comercio precisaria estar cadastrada. Um edital bom numa
plataforma sem cadastro e oportunidade perdida por cadastro, nao por preco.

O que este modulo faz, a cada rodada do radar:
 1. para cada edital relevante, le o registro da contratacao no PNCP e extrai a
    URL do sistema de origem;
 2. normaliza o dominio e compara com data/plataformas.json;
 3. dominio ja conhecido: soma uma vista e guarda a data;
 4. dominio novo: entra em "novas", com o edital que o revelou, para o Marcos
    decidir se vale cadastro. Nada e cadastrado automaticamente.

O arquivo data/plataformas.json e a fonte unica do mapa da TRX Comercio. O mapa
da TRX Diagnostico vive no repositorio dela: as duas empresas nao compartilham
cadastro, conta nem e-mail (regra de ouro de 08/11/2026).
"""
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
ARQ = os.path.join(DATA, "plataformas.json")
TZ = dt.timezone(dt.timedelta(hours=-3))

# Quantos editais consultar por rodada. O detalhe e uma chamada por edital, e a
# rodada e diaria e incremental: o que nao couber hoje aparece amanha.
TETO_CONSULTAS = int(os.environ.get("PLATAFORMAS_TETO", "40"))

# Dominios que nao sao plataforma de disputa e nao devem virar linha nova.
IGNORAR = {
    "pncp.gov.br", "www.pncp.gov.br", "gov.br", "www.gov.br",
    "transparencia.gov.br", "portaldatransparencia.gov.br",
    "in.gov.br", "imprensanacional.gov.br", "diariooficial.gov.br",
    "docs.google.com", "drive.google.com", "google.com",
    "youtube.com", "facebook.com", "instagram.com", "wa.me", "whatsapp.com",
}

# Chaves em que o PNCP ja guardou a URL do sistema de origem. A ordem importa:
# a primeira que vier preenchida vale. Se o PNCP mudar o nome do campo, o
# varredor generico abaixo ainda acha a URL.
CHAVES = ("linkSistemaOrigem", "link_sistema_origem", "linkSistemaOrigemCompra",
          "linkSistemaOrigemContratacao", "urlSistemaOrigem", "sistemaOrigem")


def agora_iso():
    return dt.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")


def dominio_de(url):
    """Dominio sem www e sem porta, vazio se nao for URL utilizavel."""
    try:
        host = urllib.parse.urlparse(str(url).strip()).hostname or ""
    except Exception:
        return ""
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return ""
    return host


# Enderecos diferentes da MESMA plataforma. Sem isto o mapa enche de linha nova
# que nao e plataforma nova: o Compras.gov.br, por exemplo, serve as paginas pelo
# SERPRO e apareceu 16 vezes na primeira rodada com outro dominio.
ALIASES = {
    "cnetmobile.estaleiro.serpro.gov.br": "compras.gov.br",
    "estaleiro.serpro.gov.br": "compras.gov.br",
    "comprasnet.gov.br": "compras.gov.br",
    "gov.br/compras": "compras.gov.br",
    "bb.com.br": "licitacoes-e.com.br",
    "licitacoes-e.bb.com.br": "licitacoes-e.com.br",
    "compras.rs.gov.br": "celic.rs.gov.br",
    "bllcompras.com": "bll.org.br",
    "bnccompras.com": "bnc.org.br",
    "licitardigital.com.br": "licitar.digital",
    "site.apoiocotacoes.com.br": "apoiocotacoes.com.br",
    "srm.paradigmabs.com.br": "paradigmabs.com.br",
}

IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def raiz_de(host):
    """Agrupa subdominio no dominio registravel, preservando os .gov.br por
    inteiro, onde o subdominio e que identifica a plataforma (compras.mg.gov.br
    e comprasnet.go.gov.br sao coisas diferentes). Endereco IP fica inteiro:
    cortar um IP em dois octetos produz lixo como "201.73"."""
    if IPV4.match(host):
        return host
    if host.endswith(".gov.br") or host.endswith(".leg.br") or host.endswith(".jus.br"):
        return ALIASES.get(host, host)
    partes = host.split(".")
    if len(partes) >= 3 and partes[-2] in ("com", "org", "net", "gov") and partes[-1] == "br":
        raiz = ".".join(partes[-3:])
    elif len(partes) >= 2:
        raiz = ".".join(partes[-2:])
    else:
        raiz = host
    # o alias pode valer para o host cheio (licitacoes-e.bb.com.br) ou para a raiz
    return ALIASES.get(host, ALIASES.get(raiz, raiz))


def _urls_no_documento(doc, achadas, profundidade=0):
    """Varredura generica: qualquer string que pareca URL http(s), a qualquer
    profundidade. Rede de seguranca para quando o PNCP renomear o campo."""
    if profundidade > 4:
        return
    if isinstance(doc, dict):
        for k, v in doc.items():
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                achadas.append((k, v))
            else:
                _urls_no_documento(v, achadas, profundidade + 1)
    elif isinstance(doc, list):
        for v in doc[:50]:
            _urls_no_documento(v, achadas, profundidade + 1)


def consultar(cnpj, ano, seq):
    """Registro da contratacao no PNCP. Devolve o dict ou None."""
    url = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
    req = urllib.request.Request(url, headers={"User-Agent": "central-trx-comercio/1.0",
                                               "Accept": "application/json"})
    for tentativa in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:
            if tentativa == 1:
                print(f"::warning::detalhe {cnpj}/{ano}/{seq} falhou: {e}")
                return None
            time.sleep(3)
    return None


def origem_de(detalhe, item):
    """(dominio, url, campo) do sistema de origem, ou ('','','') se nao houver."""
    for fonte in (detalhe, item):
        if not isinstance(fonte, dict):
            continue
        for chave in CHAVES:
            valor = fonte.get(chave)
            if isinstance(valor, str) and valor.strip():
                host = dominio_de(valor)
                if host and raiz_de(host) not in IGNORAR and host not in IGNORAR:
                    return raiz_de(host), valor.strip(), chave
    # rede de seguranca: varre o documento todo
    for fonte in (detalhe, item):
        achadas = []
        _urls_no_documento(fonte, achadas)
        for chave, valor in achadas:
            host = dominio_de(valor)
            if host and raiz_de(host) not in IGNORAR and host not in IGNORAR:
                return raiz_de(host), valor.strip(), f"{chave} (varredura)"
    return "", "", ""


def carregar():
    try:
        mapa = json.load(open(ARQ, encoding="utf-8"))
    except Exception:
        return {"conhecidas": [], "entes_regulamento_proprio": [], "novas": [],
                "estatistica": {"editais_lidos": 0, "com_origem": 0, "sem_origem": 0, "rodadas": 0}}
    return migrar(mapa)


def migrar(mapa):
    """Reaplica ALIASES e a regra de dominio ao que ja esta gravado. Serve para
    quando um alias novo revela que duas linhas eram a mesma plataforma: a linha
    nova some e a vista vai para a conhecida, sem perder contagem."""
    # funde as conhecidas que viraram alias de outra (ex.: bllcompras.com -> bll.org.br).
    # O registro canonico (aquele cujo dominio ja e o alvo) vem primeiro, para que o
    # nome e a nota que sobrevivem sejam os dele, nao os da linha alternativa.
    canonicas = sorted(mapa.get("conhecidas", []),
                       key=lambda c: ALIASES.get(c["dominio"], c["dominio"]) != c["dominio"])
    conhecidas = {}
    for c in canonicas:
        alvo = ALIASES.get(c["dominio"], c["dominio"])
        if alvo != c["dominio"] and alvo in conhecidas:
            d = conhecidas[alvo]
            d["vezes"] = int(d.get("vezes", 0)) + int(c.get("vezes", 0))
            continue
        c["dominio"] = alvo
        if alvo in conhecidas:
            d = conhecidas[alvo]
            d["vezes"] = int(d.get("vezes", 0)) + int(c.get("vezes", 0))
            continue
        conhecidas[alvo] = c

    novas = {}
    for n in mapa.get("novas", []):
        alvo = ALIASES.get(n["dominio"], n["dominio"])
        # conserta dominio truncado de rodada antiga (IP cortado em dois octetos)
        if re.match(r"^\d{1,3}\.\d{1,3}$", alvo):
            url = ((n.get("exemplos") or [{}])[0]).get("url_origem", "")
            host = dominio_de(url)
            if host:
                alvo = raiz_de(host)
        if alvo in conhecidas:
            c = conhecidas[alvo]
            c["vezes"] = int(c.get("vezes", 0)) + int(n.get("vezes", 0))
            c["visto_em"] = max(str(c.get("visto_em", "")), str(n.get("visto_em", "")))
            continue
        if alvo in novas:
            a = novas[alvo]
            a["vezes"] = int(a.get("vezes", 0)) + int(n.get("vezes", 0))
            a["exemplos"] = (a.get("exemplos", []) + n.get("exemplos", []))[:5]
            continue
        n["dominio"] = alvo
        novas[alvo] = n
    mapa["conhecidas"] = list(conhecidas.values())
    mapa["novas"] = list(novas.values())
    return mapa


def partes_do_id(item):
    """cnpj, ano, sequencial a partir do item da busca do PNCP."""
    cnpj = str(item.get("orgao_cnpj") or "").strip()
    ano, seq = item.get("ano"), item.get("numero_sequencial")
    if cnpj and ano and seq:
        return cnpj, str(ano), str(seq)
    # fallback pelo numero de controle: CNPJ-1-SEQ/ANO
    m = re.match(r"(\d{14})-\d+-(\d+)/(\d{4})", str(item.get("numero_controle_pncp") or ""))
    if m:
        return m.group(1), m.group(3), m.group(2)
    return "", "", ""


def retroalimentar(itens_brutos, hoje=None):
    """itens_brutos: lista de itens da busca do PNCP que PASSARAM no filtro de
    relevancia do radar. Grava data/plataformas.json e devolve um resumo."""
    hoje = hoje or dt.datetime.now(TZ).strftime("%Y-%m-%d")
    mapa = carregar()
    conhecidas = {c["dominio"]: c for c in mapa.get("conhecidas", [])}
    novas = {n["dominio"]: n for n in mapa.get("novas", [])}

    lidos = com_origem = sem_origem = 0
    campos = {}
    descobertas_hoje = []

    for item in itens_brutos[:TETO_CONSULTAS]:
        cnpj, ano, seq = partes_do_id(item)
        if not cnpj:
            continue
        lidos += 1
        detalhe = consultar(cnpj, ano, seq)
        dominio, url, campo = origem_de(detalhe, item)
        time.sleep(0.4)
        if not dominio:
            sem_origem += 1
            continue
        com_origem += 1
        campos[campo] = campos.get(campo, 0) + 1
        exemplo = {
            "edital": (item.get("title") or "")[:160],
            "orgao": item.get("orgao_nome") or "",
            "cidade": item.get("municipio_nome") or "",
            "uf": item.get("uf") or "",
            "link_pncp": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}",
            "url_origem": url,
            "visto_em": hoje,
        }
        if dominio in conhecidas:
            c = conhecidas[dominio]
            c["vezes"] = int(c.get("vezes", 0)) + 1
            c["visto_em"] = hoje
            continue
        if dominio in novas:
            n = novas[dominio]
            n["vezes"] = int(n.get("vezes", 0)) + 1
            n["visto_em"] = hoje
            exemplos = n.setdefault("exemplos", [])
            if len(exemplos) < 5:
                exemplos.append(exemplo)
        else:
            novas[dominio] = {
                "dominio": dominio,
                "nome": "",                     # o Marcos nomeia quando decidir
                "tipo": "a classificar",
                "situacao_comercio": "sem cadastro",
                "decisao": "a avaliar",         # a avaliar | cadastrar | ignorar
                "primeira_vez": hoje,
                "visto_em": hoje,
                "vezes": 1,
                "exemplos": [exemplo],
            }
            descobertas_hoje.append(dominio)

    est = mapa.setdefault("estatistica", {})
    est["editais_lidos"] = int(est.get("editais_lidos", 0)) + lidos
    est["com_origem"] = int(est.get("com_origem", 0)) + com_origem
    est["sem_origem"] = int(est.get("sem_origem", 0)) + sem_origem
    est["rodadas"] = int(est.get("rodadas", 0)) + 1
    est["ultima_rodada"] = agora_iso()
    if campos:
        est["campos_usados"] = campos

    mapa["conhecidas"] = sorted(conhecidas.values(),
                                key=lambda c: (c.get("prioridade", 9), c.get("nome") or c["dominio"]))
    mapa["novas"] = sorted(novas.values(), key=lambda n: (-int(n.get("vezes", 0)), n["dominio"]))
    mapa["gerado"] = agora_iso()

    os.makedirs(DATA, exist_ok=True)
    json.dump(mapa, open(ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    resumo = {"lidos": lidos, "com_origem": com_origem, "sem_origem": sem_origem,
              "descobertas": descobertas_hoje,
              "a_avaliar": [n["dominio"] for n in mapa["novas"] if n.get("decisao") == "a avaliar"]}
    print(f"OK plataformas: {lidos} editais consultados, {com_origem} com sistema de origem, "
          f"{len(descobertas_hoje)} dominio(s) novo(s): {', '.join(descobertas_hoje) or 'nenhum'}")
    return resumo


if __name__ == "__main__":
    print(json.dumps(carregar().get("estatistica", {}), ensure_ascii=False, indent=1))
