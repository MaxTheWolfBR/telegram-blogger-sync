# Sincronizador Telegram - Blogger

Sistema completo para sincronizar automaticamente um canal do Telegram com uma pagina no Blogger. Exibe fotos, videos, GIFs, documentos, audios, stickers, enquetes e localizacoes diretamente na sua pagina.

---

## O que este projeto faz

- Captura automaticamente todas as mensagens do seu canal do Telegram
- Gera um arquivo `feed.json` com todo o conteudo
- Exibe no Blogger com design moderno, responsivo e escuro (estilo Telegram)
- Suporta: **texto, fotos, videos, GIFs, documentos, audios, stickers, enquetes e localizacoes**
- Atualizacao automatica a cada 15 minutos via GitHub Actions

---

## Arquivos do Projeto

```
telegram-blogger-sync/
├── blogger-page.html      # Codigo HTML completo para colar no Blogger
├── fetch_telegram.py      # Script Python para buscar mensagens do Telegram
├── requirements.txt       # Dependencias Python
├── .github/
│   └── workflows/
│       └── sync.yml       # Automacao do GitHub Actions
├── feed.json              # Arquivo gerado com as mensagens (nao editar)
└── README.md              # Este arquivo
```

---

## Passo a Passo Completo

### ETAPA 1: Criar o Bot do Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Envie o comando `/newbot`
3. Escolha um nome e um username para o bot (deve terminar em `bot`, ex: `meu_blog_bot`)
4. Copie o **token** fornecido (algo como: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### ETAPA 2: Adicionar o Bot como Administrador do Canal

1. Va ate o seu canal **@teste2027X**
2. Clique no nome do canal > **Editar** > **Administradores**
3. Clique em **Adicionar Administrador**
4. Procure pelo nome do bot criado
5. Adicione e **de apenas a permissao de "Postar mensagens"** (ou todas, se preferir)

> **Importante:** O bot precisa ser administrador para receber as mensagens do canal!

### ETAPA 3: Criar o Repositorio no GitHub

1. Acesse [github.com/new](https://github.com/new) e crie um repositorio publico
2. De um nome como `telegram-blogger-sync`
3. **Nao inicialize** com README (ja temos um)

### ETAPA 4: Configurar os Secrets no GitHub

1. No seu repositorio, va em **Settings** > **Secrets and variables** > **Actions**
2. Clique em **New repository secret** e adicione:

| Nome | Valor |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | Token do bot fornecido pelo @BotFather |
| `TELEGRAM_CHANNEL_ID` | `-1003877652555` |

### ETAPA 5: Enviar os Arquivos para o GitHub

**Opcao A: Via interface web**
1. Na pagina do repositorio, clique em **"uploading an existing file"**
2. Arraste todos os arquivos do projeto (exceto `feed.json` e `.sync_state.json` se existirem)
3. Faça commit

**Opcao B: Via Git (terminal)**
```bash
git clone https://github.com/SEU_USUARIO/telegram-blogger-sync.git
cd telegram-blogger-sync
# Copie todos os arquivos do projeto para esta pasta
git add .
git commit -m "Primeiro commit"
git push origin main
```

### ETAPA 6: Habilitar GitHub Pages

1. No repositorio, va em **Settings** > **Pages**
2. Em **Source**, selecione **GitHub Actions**
3. A automacao ira criar a pagina automaticamente

### ETAPA 7: Obter a URL do Feed

Apos o primeiro workflow executar (ou execute manualmente em **Actions** > **Sincronizar Canal Telegram** > **Run workflow**), a URL do seu feed sera:

```
https://SEU_USUARIO.github.io/telegram-blogger-sync/feed.json
```

### ETAPA 8: Configurar a Pagina no Blogger

1. Acesse o painel do Blogger
2. Va em **Paginas** > **Nova pagina**
3. No editor, mude para modo **HTML** (clique no icone de lapis/lapis HTML)
4. Abra o arquivo `blogger-page.html` deste projeto
5. **Altere a linha 13** para a URL do seu feed:

```javascript
window.TELEGRAM_CONFIG = {
    FEED_URL: 'https://SEU_USUARIO.github.io/telegram-blogger-sync/feed.json',
    // ... resto mantem igual
};
```

6. Copie **TODO O CONTEUDO** do arquivo e cole no Blogger
7. Salve e publique!

---

## Personalizacao

### Tema Claro
Para usar tema claro, altere na configuracao:
```javascript
THEME: 'light'  // ao inves de 'dark'
```

### Itens por Pagina
```javascript
ITEMS_PER_PAGE: 20  // padrao: 10
```

### Nome do Canal
Altere no HTML nas linhas 24-25:
```html
<h1 id="tgChannelName">Nome do Seu Canal</h1>
<p>Conteudo do canal <a href="https://t.me/teste2027X">@teste2027X</a></p>
```

---

## Como Funciona

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Canal Telegram │────▶│  GitHub Actions  │────▶│   feed.json     │
│  @teste2027X    │     │  (a cada 15min)  │     │  (GitHub Pages) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                           ┌──────────────▼──────────────┐
                                           │       Pagina Blogger        │
                                           │  (JavaScript le o JSON      │
                                           │   e renderiza tudo)         │
                                           └─────────────────────────────┘
```

---

## Resolucao de Problemas

### O feed nao aparece no Blogger
- Verifique se a URL do `FEED_URL` esta correta
- Abra a URL do feed no navegador para ver se e acessivel
- No Blogger, adicione `?m=0` na URL para ver a versao desktop

### Mensagens nao aparecem
- Verifique se o bot e administrador do canal
- Verifique se os Secrets do GitHub estao corretos
- Va em **Actions** no GitHub e verifique se o workflow esta rodando sem erros

### Erro "Failed to load feed"
- O GitHub Pages pode levar alguns minutos para propagar
- Tente acessar a URL do feed diretamente no navegador

### Limite de Mensagens
- A API do bot captura ate as ultimas 1000 updates
- Para canais muito grandes, use o modo `--full` localmente

---

## Executar Localmente (Opcional)

Para testar ou forcar uma sincronizacao completa:

```bash
# Instalar dependencias
pip install -r requirements.txt

# Sincronizacao rapida (updates recentes)
python fetch_telegram.py --bot-token SEU_TOKEN --channel-id -1003877652555

# Sincronizacao completa
python fetch_telegram.py --bot-token SEU_TOKEN --channel-id -1003877652555 --full
```

---

## Recursos Suportados

| Tipo | Suporte | Descricao |
|------|---------|-----------|
| Texto | Completo | Com hashtags, mentions, links, negrito, italico |
| Fotos | Completo | Com legenda, albums (ate 10 fotos), zoom (lightbox) |
| Videos | Completo | Player HTML5 com controles |
| GIFs | Completo | Autoplay, loop, mudo |
| Documentos | Completo | Icone por tipo, tamanho, link download |
| Audio | Completo | Player com controles |
| Voz | Completo | Mensagens de voz |
| Stickers | Parcial | Estaticos (animated/video via API limitada) |
| Enquetes | Completo | Barras animadas com porcentagem |
| Localizacao | Completo | Mapa Google Maps embutido |
| Links | Completo | Preview com imagem, titulo e descricao |
| Reacoes | Completo | Emojis com contador |
| Encaminhado | Completo | Indicacao de mensagem encaminhada |
| Respostas | Completo | Contexto da conversa |

---

## Licenca

Este projeto e open-source. Use e modifique livremente.

---

**Criado com para integracao Telegram + Blogger**