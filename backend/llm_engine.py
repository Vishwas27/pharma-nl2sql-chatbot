"""
Multi-Provider LLM Engine for NL-to-SQL Conversion.
Strictly relies on real LLMs (Google Gemini, OpenAI, Groq, Anthropic).
Provides clear error handling when no API key is found or when the model service is unavailable.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from backend.domain_knowledge import build_system_prompt

load_dotenv()


class LLMEngine:
    def __init__(self):
        pass

    def generate_response(
        self,
        user_info: Dict[str, Any],
        message: str,
        conversation_history: List[Dict[str, str]] = None,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Translates a natural language question into a structured SQL response using an online LLM.
        Raises an error if no API key is found or if communication with the model fails.
        """
        load_dotenv(override=True)
        conversation_history = conversation_history or []
        system_prompt = build_system_prompt(user_info, query=message)
        from backend.rag_engine import rag_engine
        retrieved_sources = rag_engine.retrieve_relevant_context(message, top_k=3)

        # Resolve provider and API key
        provider, api_key = self._resolve_provider_and_key(provider_override, api_key_override)

        # If no API key is available, halt and report error
        if not api_key:
            raise ValueError(
                f"Server not working: No API key found for {provider.upper()}. "
                f"Please provide an API key in Settings or in your .env file."
            )

        try:
            if provider == "gemini":
                raw_result = self._call_gemini(api_key, system_prompt, conversation_history, message)
            elif provider == "openai":
                raw_result = self._call_openai(api_key, system_prompt, conversation_history, message)
            elif provider == "groq":
                raw_result = self._call_groq(api_key, system_prompt, conversation_history, message)
            elif provider == "anthropic":
                raw_result = self._call_anthropic(api_key, system_prompt, conversation_history, message)
            else:
                raise ValueError(f"Unsupported LLM provider: '{provider}'")

            if not raw_result:
                raise RuntimeError(f"Empty response returned by {provider.upper()}.")

            parsed = self._clean_and_parse_json(raw_result)
            if not parsed or "sql" not in parsed:
                raise RuntimeError(f"Invalid structured JSON format returned by {provider.upper()}.")

            parsed["rag_sources"] = retrieved_sources
            return parsed

        except Exception as e:
            err_msg = str(e)
            print(f"[LLM Engine] Provider '{provider}' error: {err_msg}")
            raise RuntimeError(
                f"Server not working: {err_msg}. Please check your API key and settings."
            )

    def _resolve_provider_and_key(self, provider_override: Optional[str], api_key_override: Optional[str]):
        """Determines the active provider and corresponding API key."""
        target_provider = (provider_override or os.getenv("LLM_PROVIDER", "gemini")).lower()

        # If an explicit API key is provided via UI/request
        if api_key_override and api_key_override.strip():
            return target_provider, api_key_override.strip()

        # Check environment keys based on provider
        if target_provider == "gemini":
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            return "gemini", key
        elif target_provider == "groq":
            return "groq", os.getenv("GROQ_API_KEY")
        elif target_provider == "openai":
            return "openai", os.getenv("OPENAI_API_KEY")
        elif target_provider == "anthropic":
            return "anthropic", os.getenv("ANTHROPIC_API_KEY")

        # Fallback to any present key
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return "gemini", os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if os.getenv("GROQ_API_KEY"):
            return "groq", os.getenv("GROQ_API_KEY")
        if os.getenv("OPENAI_API_KEY"):
            return "openai", os.getenv("OPENAI_API_KEY")
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic", os.getenv("ANTHROPIC_API_KEY")

        return target_provider, None

    def _format_history_text(self, history: List[Dict[str, Any]]) -> str:
        """Formats previous conversation turns with insights and SQL for multi-turn drill-down context."""
        parts = []
        for msg in history[-4:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            sql = msg.get("sql")
            entry = f"{role}: {content}"
            if sql:
                entry += f"\n[PREVIOUS SQL]: {sql}"
            parts.append(entry)
        return "\n\n".join(parts)

    def _call_gemini(self, api_key: str, system_prompt: str, history: List[Dict[str, str]], message: str) -> str:
        """Call Google Gemini API."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        history_text = self._format_history_text(history)
        prompt_parts = [f"SYSTEM INSTRUCTIONS & DOMAIN RULES:\n{system_prompt}"]
        if history_text:
            prompt_parts.append(f"\nCONVERSATION CONTEXT & ACTIVE ENTITIES:\n{history_text}")
        prompt_parts.append(f"\nUSER QUESTION: {message}\n\nGenerate structured JSON:")

        candidate_models = ["gemini-2.0-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
        last_err = None

        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents="\n".join(prompt_parts),
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"Gemini API call failed: {last_err}")

    def _call_openai(self, api_key: str, system_prompt: str, history: List[Dict[str, str]], message: str) -> str:
        """Call OpenAI API."""
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-4:]:
            content = msg.get("content", "")
            if msg.get("sql"):
                content += f"\n[PREVIOUS SQL]: {msg.get('sql')}"
            messages.append({"role": msg.get("role", "user"), "content": content})
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return response.choices[0].message.content

    def _call_groq(self, api_key: str, system_prompt: str, history: List[Dict[str, str]], message: str) -> str:
        """Call Groq API."""
        from groq import Groq
        client = Groq(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-4:]:
            content = msg.get("content", "")
            if msg.get("sql"):
                content += f"\n[PREVIOUS SQL]: {msg.get('sql')}"
            messages.append({"role": msg.get("role", "user"), "content": content})
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return response.choices[0].message.content

    def _call_anthropic(self, api_key: str, system_prompt: str, history: List[Dict[str, str]], message: str) -> str:
        """Call Anthropic Claude API."""
        import httpx
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        messages = []
        for msg in history[-4:]:
            content = msg.get("content", "")
            if msg.get("sql"):
                content += f"\n[PREVIOUS SQL]: {msg.get('sql')}"
            messages.append({"role": msg.get("role", "user"), "content": content})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "system": system_prompt,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.1
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    def _clean_and_parse_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM output."""
        if not raw_text:
            return None
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None
