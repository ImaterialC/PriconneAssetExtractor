#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.mtl_engine - Multi-Source Machine Translation (MTL) and Tag-Safe Preprocessing.
Supports Google (GTX), DeepL API, Local/Offline MT (Sugoi/LibreTranslate), OpenAI/LLM endpoints,
and local XUAT dictionary caching using Python standard library only (urllib.request).
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Supported engine names
MTL_ENGINES = ["Google", "DeepL", "Local / Sugoi", "LLM / OpenAI", "XUAT Cache"]

# Default system prompt for LLM translation
DEFAULT_LLM_PROMPT = (
    "You are an expert Japanese-to-English visual novel and game localization translator "
    "for 'Princess Connect! Re:Dive'. Translate the dialogue naturally while maintaining character "
    "voice and personality. Strictly preserve all placeholders and tags such as __TAG_0__, "
    "__VAR_0__, {playername}, and {0}. Output only the translated dialogue without commentary."
)


@dataclass
class MTLConfig:
    active_engine: str = "Google"
    src_lang: str = "ja"
    tgt_lang: str = "en"
    deepl_api_key: str = ""
    deepl_use_pro: bool = False
    local_mtl_url: str = "http://127.0.0.1:14366"
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen2.5:7b"
    llm_system_prompt: str = DEFAULT_LLM_PROMPT
    protect_tags: bool = True
    use_xuat_cache: bool = True
    timeout_sec: float = 12.0
    rate_limit_delay: float = 0.4
    ai_prompt_include_header: bool = True
    ai_prompt_include_speaker: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_engine": self.active_engine,
            "src_lang": self.src_lang,
            "tgt_lang": self.tgt_lang,
            "deepl_api_key": self.deepl_api_key,
            "deepl_use_pro": self.deepl_use_pro,
            "local_mtl_url": self.local_mtl_url,
            "llm_base_url": self.llm_base_url,
            "llm_api_key": self.llm_api_key,
            "llm_model": self.llm_model,
            "llm_system_prompt": self.llm_system_prompt,
            "protect_tags": self.protect_tags,
            "use_xuat_cache": self.use_xuat_cache,
            "timeout_sec": self.timeout_sec,
            "rate_limit_delay": self.rate_limit_delay,
            "ai_prompt_include_header": self.ai_prompt_include_header,
            "ai_prompt_include_speaker": self.ai_prompt_include_speaker,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MTLConfig":
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        for k in (
            "active_engine", "src_lang", "tgt_lang", "deepl_api_key", "local_mtl_url",
            "llm_base_url", "llm_api_key", "llm_model", "llm_system_prompt"
        ):
            if isinstance(data.get(k), str):
                setattr(cfg, k, data[k])
        for k in ("deepl_use_pro", "protect_tags", "use_xuat_cache", "ai_prompt_include_header", "ai_prompt_include_speaker"):
            if isinstance(data.get(k), bool):
                setattr(cfg, k, data[k])
        for k in ("timeout_sec", "rate_limit_delay"):
            if isinstance(data.get(k), (int, float)):
                setattr(cfg, k, float(data[k]))
        return cfg


class TagMasker:
    """
    Protects Princess Connect NGUI tags, playername tokens, and control sequences
    from being translated, mangled, or dropped by translation engines.
    """

    # Matches {playername}, {0}, [rub:...], [b], [i], [u], [s], [sub], [sup], [c]...[/c], [-], \n
    TOKEN_REGEX = re.compile(
        r"(\{playername\}|\{0\}|"
        r"\[rub:[^\]]+\](?:.*?)\[/rub\]|"
        r"\[c\][0-9a-fA-F]{6,8}\[/c\]|\[c\][0-9a-fA-F]{6,8}|\[/c\]|\[c\]|"
        r"\[/?(?:b|i|u|s|sub|sup)\]|\[-\]|"
        r"\\n|\r?\n)",
        re.IGNORECASE
    )

    @classmethod
    def mask(cls, text: str) -> Tuple[str, Dict[str, str]]:
        """Replace all tags with safe placeholders and return mapping."""
        tag_map: Dict[str, str] = {}
        counter = [0]

        def repl(match: re.Match) -> str:
            token = match.group(0)
            tag_id = str(counter[0])
            counter[0] += 1
            tag_map[tag_id] = token
            return f"__M_{tag_id}__"

        masked = cls.TOKEN_REGEX.sub(repl, text)
        return masked, tag_map

    @classmethod
    def unmask(cls, text: str, tag_map: Dict[str, str]) -> str:
        """Restore all original tags from placeholder tokens, resilient to MT engine spacing."""
        result = text
        for tag_id, original in tag_map.items():
            pattern = re.compile(r"__\s*[Mm]_\s*" + re.escape(tag_id) + r"\s*__")
            result = pattern.sub(lambda m, o=original: o, result)
        return result


class MTLEngine:
    """
    Unified translation client executing HTTP requests to various MTL providers.
    All calls are synchronous; use translate_async() or threading for UI responsiveness.
    """

    def __init__(self, config: Optional[MTLConfig] = None):
        self.config: MTLConfig = config or MTLConfig()
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def translate(self, text: str, config: Optional[MTLConfig] = None, xuat_cache: Optional[Dict[str, str]] = None) -> str:
        """Translate a single text string using the configured active engine."""
        cfg = config or self.config
        raw = text.strip()
        if not raw:
            return ""

        # 1. Check local XUAT translation cache first if enabled
        if cfg.use_xuat_cache and xuat_cache:
            # Check exact match
            if raw in xuat_cache:
                return xuat_cache[raw]
            # Check normalized match without whitespace
            norm_k = re.sub(r"[\s\u3000]+", "", raw)
            for k, v in xuat_cache.items():
                if re.sub(r"[\s\u3000]+", "", k) == norm_k:
                    return v

        # 2. Tag protection
        tag_map: Dict[str, str] = {}
        to_translate = text
        if cfg.protect_tags:
            to_translate, tag_map = TagMasker.mask(text)

        # 3. Route to engine
        engine_name = cfg.active_engine
        if engine_name == "Google":
            translated = self._translate_google(to_translate, cfg)
        elif engine_name == "DeepL":
            translated = self._translate_deepl(to_translate, cfg)
        elif engine_name == "Local / Sugoi":
            translated = self._translate_local(to_translate, cfg)
        elif engine_name == "LLM / OpenAI":
            translated = self._translate_llm(to_translate, cfg)
        elif engine_name == "XUAT Cache":
            if xuat_cache and raw in xuat_cache:
                return xuat_cache[raw]
            raise ValueError("No matching translation found in loaded XUAT dictionary.")
        else:
            # Fallback to Google
            translated = self._translate_google(to_translate, cfg)

        # 4. Demask tags
        if cfg.protect_tags and tag_map:
            translated = TagMasker.unmask(translated, tag_map)

        return translated

    def _translate_google(self, text: str, cfg: MTLConfig) -> str:
        """Call free Google Translate (GTX) endpoint."""
        url = (
            "https://translate.googleapis.com/translate_a/single?"
            + urllib.parse.urlencode({
                "client": "gtx",
                "sl": cfg.src_lang,
                "tl": cfg.tgt_lang,
                "dt": "t",
                "q": text,
            })
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_sec, context=self._ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data or not isinstance(data, list) or not data[0]:
                raise ValueError("Empty response from Google Translate")
            chunks = []
            for item in data[0]:
                if item and isinstance(item, list) and len(item) > 0 and item[0]:
                    chunks.append(item[0])
            return "".join(chunks)

    def _translate_deepl(self, text: str, cfg: MTLConfig) -> str:
        """Call DeepL API (Free or Pro)."""
        if not cfg.deepl_api_key.strip():
            raise ValueError("DeepL API Key is not configured. Please set it in Translator settings.")

        base_url = "https://api.deepl.com/v2/translate" if cfg.deepl_use_pro else "https://api-free.deepl.com/v2/translate"
        payload = {
            "text": [text],
            "target_lang": cfg.tgt_lang.upper(),
        }
        if cfg.src_lang and cfg.src_lang.lower() != "auto":
            payload["source_lang"] = cfg.src_lang.upper()

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            base_url,
            data=body,
            headers={
                "Authorization": f"DeepL-Auth-Key {cfg.deepl_api_key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "Misora-Story-Editor/1.3",
            }
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_sec, context=self._ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translations = data.get("translations", [])
            if not translations:
                raise ValueError("No translation returned by DeepL API")
            return translations[0].get("text", "")

    def _translate_local(self, text: str, cfg: MTLConfig) -> str:
        """Call Local Sugoi Toolkit or LibreTranslate instance."""
        url = cfg.local_mtl_url.strip()
        if not url:
            raise ValueError("Local MT URL is empty.")

        # Check if LibreTranslate format
        if "translate" in url or ":5000" in url:
            payload = {
                "q": text,
                "source": cfg.src_lang,
                "target": cfg.tgt_lang,
                "format": "text",
            }
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Misora-Local"}
            )
            with urllib.request.urlopen(req, timeout=cfg.timeout_sec, context=self._ssl_ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("translatedText", "")
        else:
            # Default Sugoi Toolkit endpoint format (port 14366)
            payload = {"message": "translate", "content": text}
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "Misora-Sugoi"}
            )
            with urllib.request.urlopen(req, timeout=cfg.timeout_sec, context=self._ssl_ctx) as resp:
                raw_resp = resp.read().decode("utf-8")
                try:
                    data = json.loads(raw_resp)
                    if isinstance(data, str):
                        return data
                    if isinstance(data, dict):
                        return data.get("translation") or data.get("result") or raw_resp
                except Exception:
                    pass
                return raw_resp.strip()

    def _translate_llm(self, text: str, cfg: MTLConfig) -> str:
        """Call OpenAI-compatible chat completion endpoint (Ollama, OpenRouter, etc.)."""
        base_url = cfg.llm_base_url.rstrip("/")
        if not base_url.endswith("/chat/completions"):
            endpoint = f"{base_url}/chat/completions"
        else:
            endpoint = base_url

        payload = {
            "model": cfg.llm_model.strip() or "qwen2.5:7b",
            "messages": [
                {"role": "system", "content": cfg.llm_system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Misora-LLM-Client",
        }
        if cfg.llm_api_key.strip():
            headers["Authorization"] = f"Bearer {cfg.llm_api_key.strip()}"

        req = urllib.request.Request(endpoint, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=cfg.timeout_sec, context=self._ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("No completions returned by LLM endpoint.")
            msg = choices[0].get("message", {})
            return msg.get("content", "").strip()

    def test_connection(self, config: Optional[MTLConfig] = None) -> Tuple[bool, str]:
        """Test the specified or active engine with a sample query."""
        cfg = config or self.config
        test_phrase = "こんにちは、騎士君！"
        try:
            res = self.translate(test_phrase, config=cfg)
            if res:
                return True, f"Success: '{test_phrase}' -> '{res}'"
            return False, "Engine returned empty response."
        except Exception as exc:
            return False, f"Connection Failed: {exc}"


def translate_async(
    text: str,
    config: MTLConfig,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
    xuat_cache: Optional[Dict[str, str]] = None,
) -> threading.Thread:
    """Run translation in a background worker thread."""
    def worker():
        try:
            engine = MTLEngine(config)
            result = engine.translate(text, config=config, xuat_cache=xuat_cache)
            on_success(result)
        except Exception as exc:
            on_error(str(exc))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t
