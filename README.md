# Central TRX Comércio

Painel da TRX COMERCIO DE PRODUTOS HOSPITALARES LTDA (CNPJ 69.495.037/0001-34),
em paralelo à Central TRX de laudos e separada dela por decisão de 12/11/2026:
cada frente tem a sua central, a sua senha e os seus documentos, mesmo quando um
documento pertence às duas empresas.

## Como funciona

- `config/dados.json` é a fonte da verdade desta fase: empresa, documentos (espelho
  do índice do repositório no Drive), acessos e links. Editar o JSON e dar push
  republica a página.
- `scripts/build.py` gera `site/dados_comercio.js`; `scripts/cifrar.py` cifra tudo
  em `site/central.enc` com o segredo `CENTRAL_SENHA` deste repositório (senha
  própria do comércio, diferente da senha da Central de laudos).
- O workflow `publicar.yml` roda a cada push e por disparo manual, e publica o
  `site/` no GitHub Pages. Sem o segredo, a rodada falha e nada sai em claro.

## Próximas fases

1. Upload de comprovantes pela própria página (app Apps Script próprio do comércio,
   gravando na pasta do Drive e registrando numa planilha).
2. Planilhas Google como fonte (documentos e licitações), lidas por conta de
   serviço, no padrão da Central de laudos.
3. Radar de licitações de produtos hospitalares.

## Acesso

Equipe com a senha: Marcos, Natália, Carla, Wagner, Ana Carolina e os sócios.
Drive direto: Marcos, Carla, Natália, Henrique e Wagner.
