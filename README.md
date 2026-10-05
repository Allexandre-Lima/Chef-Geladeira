<img width="1536" height="1024" alt="Chef de Geladeira" src="https://github.com/user-attachments/assets/158c7788-560e-42c8-aa66-11157f93b1d4" />

# Chef de Geladeira

Chatbot culinário com IA: o usuário conta o que tem em casa e o agente sugere receitas com foto, informa calorias e macronutrientes e responde dúvidas de substituição e conservação. O diferencial é o **sistema de feedback**: as avaliações dos usuários melhoram o prompt do agente, e cada nova versão só entra em uso depois de passar em **testes de regressão**.

## Funcionalidades

- **Chat** com histórico, atalhos de perguntas, cartões de receita (foto do TheMealDB) e anel de calorias (dados da USDA).
- **Agente** com Gemini, function calling, contexto de uma vector store (ChromaDB) e prompt versionado.
- **Feedback e melhoria**: formulário de captura, prompt atual, histórico de versões com diff, motivo de cada teste de regressão e rollback.
- **Atualização automática do prompt** a cada N feedbacks (configurável), em segundo plano, além do botão manual.
- **Guardrails** de entrada (tamanho e prompt injection), de saída (aviso de alergia) e de atualização do prompt.
- **Resiliência**: tentativas com espera em caso de sobrecarga e troca automática de modelo Gemini.

## Arquitetura

```
Navegador (HTML + CSS + JavaScript, sem build)
        │  /            arquivos estáticos
        ▼  /api/*       JSON
FastAPI (um único container)
  ├─ api/          rotas HTTP
  ├─ agent/        Gemini, function calling, regras de retry e troca de modelo
  ├─ tools/        TheMealDB e USDA FoodData Central
  ├─ vectorstore/  ChromaDB (base de conhecimento culinária)
  ├─ feedback/     análise → proposta → regressão (em segundo plano)
  ├─ prompts/      versões do prompt e feedbacks (SQLite)
  └─ guardrails/   validações de entrada, saída e de prompt
```

## Como o feedback melhora o prompt

1. O usuário avalia uma resposta (Boa/Ruim e uma sugestão) no chat ou na aba **Feedback e melhoria**.
2. Quando há `AUTO_IMPROVE_THRESHOLD` feedbacks úteis (com comentário ou nota negativa), a análise começa sozinha. Também dá para iniciá-la com **Analisar agora**.
3. Um LLM classifica cada feedback (tom, formato, precisão, uso de ferramentas, escopo).
4. Outro passo propõe uma nova seção de **estilo** do prompt, repetindo literalmente pedidos como "2 receitas" ou "3 passos". As **regras fixas** (escopo, alergias, uso de ferramentas) ficam em outra seção e nunca são alteradas.
5. Guardrails validam a proposta (tamanho, prompt injection, tentativa de redefinir regras fixas).
6. O prompt candidato é reexecutado contra respostas mal avaliadas do histórico e um LLM-juiz avalia cada resultado (**teste de regressão**).
7. Com aprovação ≥ `REGRESSION_PASS_THRESHOLD` (padrão 80%), a versão é ativada. Caso contrário, é salva como **rejeitada**, com o motivo de cada caso.
8. Qualquer versão pode ser comparada (diff) e reativada (rollback).

## Executar com Docker

Pré-requisito: Docker Desktop em execução e uma chave gratuita do Gemini (https://aistudio.google.com/apikey).

```bash
cp .env.example .env     # preencha GEMINI_API_KEY
docker compose up --build
```

Abra http://localhost:8000. Os dados (SQLite e ChromaDB) ficam em `./data` e sobrevivem a reinícios.

## Executar sem Docker (opcional)

Requer Python 3.9+ (as versões fixadas em `requirements.txt` foram testadas com Python 3.11, o mesmo da imagem Docker).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # preencha GEMINI_API_KEY
uvicorn app.main:app --port 8000
```

## Configuração (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | (vazio) | Chave do Gemini. Obrigatória. |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Modelo principal. |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite` | Alternativos, usados se o principal estiver sem acesso, sem cota ou sobrecarregado. |
| `USDA_API_KEY` | `DEMO_KEY` | Chave da USDA. A `DEMO_KEY` tem limite de 30 consultas por hora. |
| `AUTO_IMPROVE` | `true` | Liga a atualização automática do prompt. |
| `AUTO_IMPROVE_THRESHOLD` | `3` | Feedbacks úteis necessários para a análise automática. |
| `REGRESSION_PASS_THRESHOLD` | `0.8` | Aprovação mínima na regressão para ativar uma versão. |

## Exemplos de uso

- "Tenho frango, arroz e cenoura. O que posso fazer?" (cartões de receita)
- "Quantas calorias tem 100 g de leite condensado?" (anel de calorias)
- "Não tenho ovo. O que uso no bolo?" (base de conhecimento)
- Depois de avaliar algumas respostas ("quero só 2 receitas com 3 passos cada"), acompanhe a análise na aba **Feedback e melhoria**.

## APIs utilizadas

| API | Uso | Autenticação |
|---|---|---|
| Google Gemini | LLM, function calling e embeddings | chave gratuita |
| TheMealDB (`filter.php`, `lookup.php`) | receitas por ingrediente, foto e detalhes | chave pública de teste |
| USDA FoodData Central (`/fdc/v1/foods/search`) | calorias e macros por 100 g | `USDA_API_KEY` (padrão `DEMO_KEY`) |

### Endpoints do backend

`GET /api/health` · `POST /api/chat` · `POST /api/feedback` · `GET /api/feedback` · `GET /api/prompts` · `GET /api/prompts/status` · `POST /api/prompts/improve` · `POST /api/prompts/{versão}/activate`

A documentação interativa fica em http://localhost:8000/docs.

## Testes

```bash
docker compose run --rm app python -m pytest -q
```

Cobrem guardrails, repositório de prompts (incluindo migração do banco), ferramentas externas (com HTTP simulado), regras de retry e troca de modelo, extração dos resultados das ferramentas e rotas da API.

## Decisões e suposições

- **Frontend em HTML, CSS e JavaScript puros**, servido pelo próprio FastAPI: um só container, sem etapa de build e com controle total do visual.
- **Apenas 2 APIs externas (o mínimo exigido), ambas de alimentos**: TheMealDB e USDA. Menos integrações significam menos pontos de falha e menos consumo da cota gratuita. A API Open Food Facts foi testada e descartada porque a busca ficou indisponível para acessos anônimos.
- **Backend sem estado de conversa**: o histórico vem do navegador a cada requisição.
- **Só a seção de estilo do prompt é editável** pelo feedback; regras de segurança são fixas.
- **A análise roda em segundo plano** (uma por vez), pois leva minutos por causa dos testes de regressão. O navegador acompanha o andamento.
- **Feedbacks analisados não são reanalisados**, mesmo quando a versão gerada é rejeitada. Eles continuam no histórico e alimentam os testes de regressão futuros.
- **Sugestões gerais** (sem resposta associada) entram na análise, mas não viram caso de teste de regressão.
- **O aviso de alergia é anexado por código**, não depende do modelo.
- **TheMealDB gratuito filtra um ingrediente por vez** e tem catálogo em inglês; o agente traduz as respostas e complementa com a base de conhecimento.
- Falhas em APIs externas viram mensagens de erro tratadas, nunca exceções para o usuário.

## Limitações e próximos passos

- Sem autenticação nem perfis: é um projeto de demonstração.
- O cartão de receita mostra foto, nome e botão; tempo, dificuldade e calorias não são fornecidos pelo TheMealDB.
- Ideias futuras: cadastro do estoque da geladeira com validade, favoritos, histórico de conversas por usuário e tradução das receitas.
- A cota gratuita do Gemini limita quantas análises de regressão cabem por dia.
