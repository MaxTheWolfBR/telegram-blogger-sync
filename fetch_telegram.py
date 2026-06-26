#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sincronizador de Canal Telegram -> JSON Feed
Busca mensagens de um canal do Telegram e gera um arquivo JSON para consumo no Blogger.

Uso:
    python fetch_telegram.py --bot-token SEU_BOT_TOKEN --channel -1003877652555

Ou defina as variáveis de ambiente:
    TELEGRAM_BOT_TOKEN=seu_token
    TELEGRAM_CHANNEL_ID=-1003877652555
"""

import os
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import aiofiles


# ============================== CONFIGURAÇÕES ==============================

# ID do canal (fornecido pelo usuário)
DEFAULT_CHANNEL_ID = -1003877652555

# Máximo de mensagens por execução (Telegram limita a 100 por request)
MESSAGES_PER_REQUEST = 100
MAX_TOTAL_MESSAGES = 1000  # Limite de segurança

# Arquivo de saída
OUTPUT_FILE = Path(__file__).parent / "feed.json"
STATE_FILE = Path(__file__).parent / ".sync_state.json"

# Delay entre requests para evitar rate limit
REQUEST_DELAY = 0.5


# ============================== CLASSE PRINCIPAL ==============================

class TelegramFeedSync:
    def __init__(self, bot_token: str, channel_id: int):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = None
        self.messages = []
        self.stats = {
            "total": 0,
            "photos": 0,
            "videos": 0,
            "documents": 0,
            "audios": 0,
            "voices": 0,
            "stickers": 0,
            "polls": 0,
            "locations": 0,
            "text": 0,
            "animations": 0,
            "errors": 0
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            headers={"Content-Type": "application/json"}
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    # ----- API Methods -----

    async def api_request(self, method: str, params: dict = None) -> dict:
        """Faz uma request à API do Telegram."""
        url = f"{self.base_url}/{method}"
        params = params or {}

        try:
            if method in ["sendDocument", "sendPhoto", "sendVideo"]:
                # Para uploads (não usado aqui)
                async with self.session.post(url, data=params) as resp:
                    result = await resp.json()
            else:
                async with self.session.post(url, json=params) as resp:
                    result = await resp.json()

            if not result.get("ok"):
                error_code = result.get("error_code", "unknown")
                description = result.get("description", "Unknown error")
                print(f"  ⚠️ API Error {error_code}: {description}")
                self.stats["errors"] += 1
                return {}

            return result.get("result", {})

        except asyncio.TimeoutError:
            print(f"  ⚠️ Timeout na request {method}")
            self.stats["errors"] += 1
            return {}
        except Exception as e:
            print(f"  ⚠️ Erro na request {method}: {e}")
            self.stats["errors"] += 1
            return {}

    async def get_chat_info(self) -> dict:
        """Obtém informações do canal."""
        print("📋 Obtendo informações do canal...")
        result = await self.api_request("getChat", {"chat_id": self.channel_id})
        if result:
            print(f"   ✅ Canal: {result.get('title', 'Desconhecido')}")
            print(f"   👥 Membros: {result.get('members_count', 'N/A')}")
        return result

    async def get_updates(self, offset: int = None, limit: int = 100) -> list:
        """Obtém updates do bot."""
        params = {"limit": limit}
        if offset:
            params["offset"] = offset
        return await self.api_request("getUpdates", params)

    async def forward_messages_to_bot(self, message_ids: list) -> list:
        """
        Encaminha mensagens do canal para o bot para obter conteúdo completo.
        Esta é a forma mais confiável de obter todas as mensagens.
        """
        forwarded = []
        # Criar um grupo privado ou usar o chat do próprio bot
        # Primeiro, obter o chat_id do bot
        me = await self.api_request("getMe", {})
        if not me:
            return []

        bot_id = me.get("id")

        # Tentar encaminhar mensagens para o próprio bot (não funciona diretamente)
        # Solução alternativa: usar getUpdates para capturar mensagens novas
        # Ou: usar o método de cópia de mensagens

        for msg_id in message_ids:
            try:
                # Tentar copiar a mensagem para o chat do bot
                result = await self.api_request("copyMessage", {
                    "chat_id": bot_id,
                    "from_chat_id": self.channel_id,
                    "message_id": msg_id
                })
                if result:
                    forwarded.append(result.get("message_id"))
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"  ⚠️ Erro ao copiar msg {msg_id}: {e}")

        return forwarded

    async def get_chat_history(self, limit: int = 100, from_message_id: int = None) -> list:
        """
        Obtém histórico de mensagens do canal.
        Nota: A API oficial do bot NÃO tem método getHistory diretamente.
        Precisamos usar workarounds.
        """
        # Método 1: Tentar usar getUpdates e filtrar pelo canal
        # Isso só funciona para mensagens recentes que o bot ainda não processou

        # Método 2: Usar copyMessage para copiar mensagens para um chat conhecido
        # e depois ler de lá

        # Método 3: Se o bot é admin do canal, usar getUpdates com allowed_updates

        print("📥 Buscando mensagens do canal...")

        # Primeiro, tentar obter updates que mencionam o canal
        updates = await self.get_updates(limit=100)

        messages = []
        channel_msgs = []

        for update in updates:
            msg = update.get("message") or update.get("channel_post")
            if msg and msg.get("chat", {}).get("id") == self.channel_id:
                channel_msgs.append(msg)

        if channel_msgs:
            print(f"   ✅ Encontradas {len(channel_msgs)} mensagens via getUpdates")
            return channel_msgs

        # Se não conseguiu via updates, tentar outra abordagem
        print("   ⚠️ Nenhuma mensagem nova via getUpdates")
        print("   💡 Para obter histórico completo, use um dos métodos alternativos:")
        print("      1. API TDLib (mais completa)")
        print("      2. MTProto API direta")
        print("      3. Bot como admin + webhook para capturar novas mensagens")

        return []

    # ----- Processamento de Mensagens -----

    def extract_message_data(self, msg: dict) -> dict:
        """Extrai dados relevantes de uma mensagem do Telegram."""
        if not msg:
            return None

        msg_id = msg.get("message_id", 0)
        date_str = msg.get("date", "")

        # Converter timestamp Unix para ISO
        if isinstance(date_str, (int, float)):
            date_iso = datetime.fromtimestamp(date_str, tz=timezone.utc).isoformat()
        else:
            date_iso = date_str

        # Texto
        text = msg.get("text", "") or msg.get("caption", "")

        # Entidades de formatação
        entities = msg.get("entities", []) or msg.get("caption_entities", [])
        formatted_text = self.apply_entities(text, entities)

        # Autor
        sender = msg.get("from", {})
        sender_chat = msg.get("sender_chat", {})
        author = {
            "id": sender.get("id"),
            "first_name": sender.get("first_name", ""),
            "last_name": sender.get("last_name", ""),
            "username": sender.get("username", ""),
            "is_bot": sender.get("is_bot", False)
        }

        # Dados da mensagem
        data = {
            "message_id": msg_id,
            "date": date_iso,
            "timestamp": date_str if isinstance(date_str, (int, float)) else None,
            "text": text,
            "formatted_text": formatted_text,
            "from": author,
            "sender_chat": {
                "id": sender_chat.get("id"),
                "title": sender_chat.get("title", ""),
                "username": sender_chat.get("username", ""),
                "type": sender_chat.get("type", "")
            },
            "views": msg.get("views", 0),
            "forwards": msg.get("forward_count", 0),
            "reactions": self.extract_reactions(msg.get("reactions", [])),
            "reply_to_message": None,
            "forward_from": None,
            "media_group_id": msg.get("media_group_id"),
            "edit_date": msg.get("edit_date"),
        }

        # Reply
        if msg.get("reply_to_message"):
            data["reply_to_message"] = {
                "message_id": msg["reply_to_message"].get("message_id"),
                "text": msg["reply_to_message"].get("text", "") or msg["reply_to_message"].get("caption", ""),
                "from": {
                    "first_name": msg["reply_to_message"].get("from", {}).get("first_name", "Usuário")
                }
            }

        # Forward
        if msg.get("forward_from") or msg.get("forward_from_chat"):
            data["forward_from"] = {
                "name": (
                    msg.get("forward_from_chat", {}).get("title") or
                    msg.get("forward_from", {}).get("first_name", "Desconhecido")
                ),
                "date": msg.get("forward_date")
            }

        # Extrair mídia específica
        self.extract_media(msg, data)

        return data

    def extract_media(self, msg: dict, data: dict):
        """Extrai informações de mídia da mensagem."""

        # Foto
        if "photo" in msg:
            photos = []
            for photo in msg["photo"]:
                photos.append({
                    "file_id": photo.get("file_id", ""),
                    "file_unique_id": photo.get("file_unique_id", ""),
                    "width": photo.get("width", 0),
                    "height": photo.get("height", 0),
                    "file_size": photo.get("file_size", 0),
                    "file_url": None  # Será preenchido se obtivermos o arquivo
                })
            data["photo"] = photos
            self.stats["photos"] += 1

        # Vídeo
        if "video" in msg:
            video = msg["video"]
            data["video"] = {
                "file_id": video.get("file_id", ""),
                "file_unique_id": video.get("file_unique_id", ""),
                "width": video.get("width", 0),
                "height": video.get("height", 0),
                "duration": video.get("duration", 0),
                "mime_type": video.get("mime_type", "video/mp4"),
                "file_size": video.get("file_size", 0),
                "file_name": video.get("file_name", ""),
                "thumbnail": self.extract_thumbnail(video.get("thumb")),
                "file_url": None
            }
            self.stats["videos"] += 1

        # Animação (GIF)
        if "animation" in msg:
            anim = msg["animation"]
            data["animation"] = {
                "file_id": anim.get("file_id", ""),
                "file_unique_id": anim.get("file_unique_id", ""),
                "width": anim.get("width", 0),
                "height": anim.get("height", 0),
                "duration": anim.get("duration", 0),
                "mime_type": anim.get("mime_type", "video/mp4"),
                "file_size": anim.get("file_size", 0),
                "file_name": anim.get("file_name", ""),
                "thumbnail": self.extract_thumbnail(anim.get("thumb")),
                "file_url": None
            }
            self.stats["animations"] += 1

        # Documento
        if "document" in msg:
            doc = msg["document"]
            data["document"] = {
                "file_id": doc.get("file_id", ""),
                "file_unique_id": doc.get("file_unique_id", ""),
                "file_name": doc.get("file_name", "Documento"),
                "mime_type": doc.get("mime_type", "application/octet-stream"),
                "file_size": doc.get("file_size", 0),
                "thumbnail": self.extract_thumbnail(doc.get("thumb")),
                "file_url": None
            }
            self.stats["documents"] += 1

        # Áudio
        if "audio" in msg:
            audio = msg["audio"]
            data["audio"] = {
                "file_id": audio.get("file_id", ""),
                "file_unique_id": audio.get("file_unique_id", ""),
                "duration": audio.get("duration", 0),
                "performer": audio.get("performer", ""),
                "title": audio.get("title", ""),
                "mime_type": audio.get("mime_type", "audio/mpeg"),
                "file_size": audio.get("file_size", 0),
                "file_url": None
            }
            self.stats["audios"] += 1

        # Voz
        if "voice" in msg:
            voice = msg["voice"]
            data["voice"] = {
                "file_id": voice.get("file_id", ""),
                "file_unique_id": voice.get("file_unique_id", ""),
                "duration": voice.get("duration", 0),
                "mime_type": voice.get("mime_type", "audio/ogg"),
                "file_size": voice.get("file_size", 0),
                "file_url": None
            }
            self.stats["voices"] += 1

        # Sticker
        if "sticker" in msg:
            sticker = msg["sticker"]
            data["sticker"] = {
                "file_id": sticker.get("file_id", ""),
                "file_unique_id": sticker.get("file_unique_id", ""),
                "width": sticker.get("width", 0),
                "height": sticker.get("height", 0),
                "is_animated": sticker.get("is_animated", False),
                "is_video": sticker.get("is_video", False),
                "emoji": sticker.get("emoji", ""),
                "set_name": sticker.get("set_name", ""),
                "thumbnail": self.extract_thumbnail(sticker.get("thumb")),
                "file_url": None
            }
            self.stats["stickers"] += 1

        # Enquete
        if "poll" in msg:
            poll = msg["poll"]
            data["poll"] = {
                "id": poll.get("id", ""),
                "question": poll.get("question", ""),
                "options": [
                    {
                        "text": opt.get("text", ""),
                        "voter_count": opt.get("voter_count", 0)
                    }
                    for opt in poll.get("options", [])
                ],
                "total_voter_count": poll.get("total_voter_count", 0),
                "is_closed": poll.get("is_closed", False),
                "allows_multiple_answers": poll.get("allows_multiple_answers", False),
                "type": poll.get("type", "regular")
            }
            self.stats["polls"] += 1

        # Localização
        if "location" in msg:
            loc = msg["location"]
            data["location"] = {
                "latitude": loc.get("latitude", 0),
                "longitude": loc.get("longitude", 0),
                "horizontal_accuracy": loc.get("horizontal_accuracy")
            }
            self.stats["locations"] += 1

        # Venue (local com nome)
        if "venue" in msg:
            venue = msg["venue"]
            data["venue"] = {
                "title": venue.get("title", ""),
                "address": venue.get("address", ""),
                "location": {
                    "latitude": venue.get("location", {}).get("latitude", 0),
                    "longitude": venue.get("location", {}).get("longitude", 0)
                }
            }
            self.stats["locations"] += 1

        # Link preview
        if "web_page" in msg:
            wp = msg["web_page"]
            data["web_page"] = {
                "url": wp.get("url", ""),
                "display_url": wp.get("display_url", ""),
                "type": wp.get("type", ""),
                "site_name": wp.get("site_name", ""),
                "title": wp.get("title", ""),
                "description": wp.get("description", ""),
                "photo": self.extract_webpage_photo(wp.get("photo"))
            }

        # Se não tem nenhuma mídia especial, conta como texto
        if not any(k in data for k in ["photo", "video", "animation", "document",
                                        "audio", "voice", "sticker", "poll", "location", "venue"]):
            self.stats["text"] += 1

    def extract_thumbnail(self, thumb: dict) -> str:
        """Extrai file_id da thumbnail."""
        if not thumb:
            return ""
        return thumb.get("file_id", "")

    def extract_webpage_photo(self, photo: dict) -> list:
        """Extrai fotos de preview de webpage."""
        if not photo:
            return []
        if isinstance(photo, list):
            return [{"file_id": p.get("file_id"), "width": p.get("width"),
                    "height": p.get("height")} for p in photo]
        if isinstance(photo, dict):
            sizes = photo.get("sizes", [])
            return [{"file_id": s.get("file_id"), "width": s.get("width"),
                    "height": s.get("height")} for s in sizes]
        return []

    def extract_reactions(self, reactions: list) -> list:
        """Extrai reações da mensagem."""
        if not reactions:
            return []

        result = []
        # Formato novo da API
        reaction_list = reactions if isinstance(reactions, list) else reactions.get("reactions", [])

        for reaction in reaction_list:
            if isinstance(reaction, dict):
                emoji = reaction.get("emoji", reaction.get("type", {}).get("emoji", "❤"))
                count = reaction.get("total_count", reaction.get("count", 0))
                result.append({"emoji": emoji, "count": count})

        return result

    def apply_entities(self, text: str, entities: list) -> str:
        """Aplica formatação de entidades ao texto."""
        if not entities or not text:
            return text or ""

        # Simples: retorna o texto com markdown básico
        result = text
        offset_adjust = 0

        for entity in sorted(entities, key=lambda e: e.get("offset", 0)):
            e_type = entity.get("type", "")
            offset = entity.get("offset", 0)
            length = entity.get("length", 0)

            # Este é um processamento simplificado
            # Na prática, o HTML do Blogger faz a formatação

        return result

    # ----- File URL Resolution -----

    async def resolve_file_urls(self, messages: list):
        """
        Resolve file_ids para URLs diretas usando getFile.
        NOTA: As URLs do Telegram expiram! Ideal para processamento imediato.
        """
        print("\n🔗 Resolvendo URLs de arquivos...")
        resolved = 0

        for msg in messages:
            # Resolver fotos
            if "photo" in msg:
                for photo in msg["photo"]:
                    if photo.get("file_id") and not photo.get("file_url"):
                        url = await self.get_file_url(photo["file_id"])
                        if url:
                            photo["file_url"] = url
                            resolved += 1
                            await asyncio.sleep(0.05)

            # Resolver vídeos
            if "video" in msg and msg["video"].get("file_id"):
                url = await self.get_file_url(msg["video"]["file_id"])
                if url:
                    msg["video"]["file_url"] = url
                    resolved += 1
                await asyncio.sleep(0.05)

            # Resolver animações
            if "animation" in msg and msg["animation"].get("file_id"):
                url = await self.get_file_url(msg["animation"]["file_id"])
                if url:
                    msg["animation"]["file_url"] = url
                    resolved += 1
                await asyncio.sleep(0.05)

            # Resolver documentos
            if "document" in msg and msg["document"].get("file_id"):
                url = await self.get_file_url(msg["document"]["file_id"])
                if url:
                    msg["document"]["file_url"] = url
                    resolved += 1
                await asyncio.sleep(0.05)

            # Resolver áudios
            if "audio" in msg and msg["audio"].get("file_id"):
                url = await self.get_file_url(msg["audio"]["file_id"])
                if url:
                    msg["audio"]["file_url"] = url
                    resolved += 1
                await asyncio.sleep(0.05)

            # Resolver vozes
            if "voice" in msg and msg["voice"].get("file_id"):
                url = await self.get_file_url(msg["voice"]["file_id"])
                if url:
                    msg["voice"]["file_url"] = url
                    resolved += 1
                await asyncio.sleep(0.05)

        print(f"   ✅ {resolved} arquivos resolvidos")

    async def get_file_url(self, file_id: str) -> str:
        """Obtém URL direta de um arquivo via getFile."""
        if not file_id:
            return None

        result = await self.api_request("getFile", {"file_id": file_id})
        if result and result.get("file_path"):
            return f"https://api.telegram.org/file/bot{self.bot_token}/{result['file_path']}"
        return None

    # ----- Main Processing -----

    async def process_updates(self):
        """
        Processa updates do bot para obter mensagens do canal.
        Este método captura mensagens que o bot recebe como administrador do canal.
        """
        print("=" * 60)
        print("🚀 INICIANDO SINCRONIZAÇÃO DO CANAL TELEGRAM")
        print("=" * 60)
        print(f"📢 Canal ID: {self.channel_id}")

        # Obter info do canal
        chat_info = await self.get_chat_info()
        channel_title = chat_info.get("title", "Canal") if chat_info else "Canal"

        # Carregar estado anterior
        last_update_id = 0
        existing_messages = []

        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    last_update_id = state.get("last_update_id", 0)
                    # Carregar mensagens existentes
                    if OUTPUT_FILE.exists():
                        with open(OUTPUT_FILE, 'r', encoding='utf-8') as of:
                            existing_data = json.load(of)
                            existing_messages = existing_data.get("messages", [])
                            print(f"📚 {len(existing_messages)} mensagens já existentes no feed")
            except Exception as e:
                print(f"   ⚠️ Erro ao carregar estado: {e}")

        # Obter updates
        updates = await self.get_updates(offset=last_update_id + 1 if last_update_id else None, limit=100)

        if not updates:
            print("   ℹ️ Nenhuma nova mensagem encontrada")
            # Salvar feed existente mesmo sem updates
            if existing_messages:
                await self.save_feed(existing_messages, channel_title)
            return

        print(f"   📥 {len(updates)} updates recebidos")

        # Processar mensagens do canal
        new_messages = []
        max_update_id = last_update_id

        for update in updates:
            update_id = update.get("update_id", 0)
            if update_id > max_update_id:
                max_update_id = update_id

            # Verificar se é uma mensagem do canal
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                continue

            chat = msg.get("chat", {})
            if chat.get("id") != self.channel_id:
                continue

            processed = self.extract_message_data(msg)
            if processed:
                new_messages.append(processed)
                print(f"   ➕ Mensagem {processed['message_id']}: {getMessageTypeLabel(processed)}")

        print(f"\n📊 {len(new_messages)} novas mensagens do canal")

        # Mesclar com mensagens existentes (evitar duplicatas)
        all_messages = merge_messages(existing_messages, new_messages)

        # Resolver URLs de arquivos
        await self.resolve_file_urls(all_messages)

        # Salvar feed
        await self.save_feed(all_messages, channel_title)

        # Salvar estado
        state = {
            "last_update_id": max_update_id,
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "channel_id": self.channel_id,
            "total_messages": len(all_messages)
        }

        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        # Print estatísticas
        print("\n" + "=" * 60)
        print("📈 ESTATÍSTICAS")
        print("=" * 60)
        for key, value in self.stats.items():
            if value > 0:
                print(f"   {key.capitalize()}: {value}")
        print(f"\n✅ Total: {len(all_messages)} mensagens no feed")
        print(f"📁 Feed salvo em: {OUTPUT_FILE.absolute()}")
        print(f"📁 Estado salvo em: {STATE_FILE.absolute()}")

    async def process_all_history_tdlib(self):
        """
        Método alternativo usando abordagem de exportação.
        Este método tenta obter o máximo de mensagens possível.
        """
        print("=" * 60)
        print("🚀 SINCRONIZAÇÃO COMPLETA DO CANAL")
        print("=" * 60)
        print("Este método usa a API de updates do bot.")
        print("Para histórico completo, considere usar a API MTProto.")
        print("")

        # Carregar mensagens existentes
        existing_messages = []
        if OUTPUT_FILE.exists():
            try:
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_messages = data.get("messages", [])
                    print(f"📚 {len(existing_messages)} mensagens existentes")
            except:
                pass

        # Obter todas as updates possíveis
        all_updates = []
        offset = None

        print("📥 Buscando todas as updates disponíveis...")
        for i in range(10):  # Máximo 1000 updates
            updates = await self.get_updates(offset=offset, limit=100)
            if not updates:
                break

            all_updates.extend(updates)
            offset = max(u.get("update_id", 0) for u in updates) + 1

            if len(updates) < 100:
                break

            print(f"   Lote {i+1}: {len(updates)} updates (total: {len(all_updates)})")
            await asyncio.sleep(0.5)

        print(f"\n📦 Total de updates obtidas: {len(all_updates)}")

        # Filtrar apenas mensagens do canal
        channel_messages = []
        seen_ids = set()

        for update in all_updates:
            msg = update.get("channel_post") or update.get("message")
            if not msg:
                continue

            chat = msg.get("chat", {})
            if chat.get("id") != self.channel_id:
                continue

            msg_id = msg.get("message_id")
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)

            processed = self.extract_message_data(msg)
            if processed:
                channel_messages.append(processed)

        print(f"📊 {len(channel_messages)} mensagens do canal encontradas")

        # Mesclar com existentes
        all_messages = merge_messages(existing_messages, channel_messages)

        # Resolver URLs
        await self.resolve_file_urls(all_messages)

        # Obter info do canal
        chat_info = await self.get_chat_info()
        channel_title = chat_info.get("title", "Canal") if chat_info else "Canal"

        # Salvar
        await self.save_feed(all_messages, channel_title)

        # Salvar estado
        state = {
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "channel_id": self.channel_id,
            "total_messages": len(all_messages)
        }

        if all_updates:
            state["last_update_id"] = max(u.get("update_id", 0) for u in all_updates)

        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Feed atualizado: {len(all_messages)} mensagens")

    async def save_feed(self, messages: list, channel_title: str):
        """Salva o feed no arquivo JSON."""
        feed = {
            "channel": {
                "id": self.channel_id,
                "title": channel_title,
                "username": "teste2027X",
                "url": f"https://t.me/teste2027X",
                "type": "channel"
            },
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_messages": len(messages),
                "version": "2.0"
            },
            "messages": messages
        }

        async with aiofiles.open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(feed, ensure_ascii=False, indent=2))


# ============================== FUNÇÕES AUXILIARES ==============================

def getMessageTypeLabel(msg: dict) -> str:
    """Retorna label do tipo de mensagem."""
    if "photo" in msg: return "📷 Foto"
    if "video" in msg: return "🎥 Vídeo"
    if "animation" in msg: return "🎬 GIF"
    if "document" in msg: return "📄 Documento"
    if "audio" in msg: return "🎵 Áudio"
    if "voice" in msg: return "🎤 Voz"
    if "sticker" in msg: return "😊 Sticker"
    if "poll" in msg: return "📊 Enquete"
    if "location" in msg: return "📍 Localização"
    if "venue" in msg: return "📍 Local"
    return "💬 Texto"


def merge_messages(existing: list, new_msgs: list) -> list:
    """Mescla mensagens evitando duplicatas por message_id."""
    seen = set()
    merged = []

    # Adicionar existentes primeiro
    for msg in existing:
        msg_id = msg.get("message_id")
        if msg_id and msg_id not in seen:
            seen.add(msg_id)
            merged.append(msg)

    # Adicionar novas (substituem se já existirem - atualização)
    for msg in new_msgs:
        msg_id = msg.get("message_id")
        if msg_id:
            if msg_id in seen:
                # Substituir mensagem existente (atualizada)
                for i, existing_msg in enumerate(merged):
                    if existing_msg.get("message_id") == msg_id:
                        merged[i] = msg
                        break
            else:
                seen.add(msg_id)
                merged.append(msg)

    # Ordenar por message_id (cronológico)
    merged.sort(key=lambda m: m.get("message_id", 0), reverse=True)

    return merged


# ============================== MAIN ==============================

async def main():
    parser = argparse.ArgumentParser(description='Sincroniza canal Telegram com feed JSON')
    parser.add_argument('--bot-token', default=os.environ.get('TELEGRAM_BOT_TOKEN'),
                       help='Token do bot do Telegram')
    parser.add_argument('--channel-id', type=int,
                       default=int(os.environ.get('TELEGRAM_CHANNEL_ID', DEFAULT_CHANNEL_ID)),
                       help='ID do canal (ex: -1003877652555)')
    parser.add_argument('--full', action='store_true',
                       help='Sincronização completa (tenta obter todo histórico)')
    parser.add_argument('--output', default=str(OUTPUT_FILE),
                       help='Caminho do arquivo de saída')

    args = parser.parse_args()

    if not args.bot_token:
        print("❌ ERRO: Token do bot não fornecido!")
        print("\nFormas de fornecer o token:")
        print("  1. Argumento: --bot-token SEU_TOKEN")
        print("  2. Variável de ambiente: TELEGRAM_BOT_TOKEN=SEU_TOKEN")
        print("\nPara criar um bot:")
        print("  1. Abra o @BotFather no Telegram")
        print("  2. Envie /newbot e siga as instruções")
        print("  3. Copie o token fornecido")
        sys.exit(1)

    # Override output path if provided
    global OUTPUT_FILE
    OUTPUT_FILE = Path(args.output)

    async with TelegramFeedSync(args.bot_token, args.channel_id) as sync:
        if args.full:
            await sync.process_all_history_tdlib()
        else:
            await sync.process_updates()


if __name__ == "__main__":
    asyncio.run(main())