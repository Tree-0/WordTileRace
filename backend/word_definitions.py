from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
TIMEOUT_SECONDS = 5


class DefinitionLookupError(RuntimeError):
    """Raised when the dictionary service cannot be queried successfully."""


def normalize_word(word: str) -> str:
    normalized = word.strip().upper()
    if not normalized.isalpha():
        raise ValueError("Word must contain only A-Z letters.")
    return normalized


def parse_definition_response(payload: Any, word: str) -> dict[str, Any]:
    normalized = normalize_word(word)
    meanings = []

    if not isinstance(payload, list):
        return {"word": normalized, "meanings": meanings}

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        entry_meanings = entry.get("meanings", [])
        if not isinstance(entry_meanings, list):
            continue

        for meaning in entry_meanings:
            if not isinstance(meaning, dict):
                continue

            definitions = []
            meaning_definitions = meaning.get("definitions", [])
            if not isinstance(meaning_definitions, list):
                continue

            for definition in meaning_definitions:
                if not isinstance(definition, dict):
                    continue

                definition_text = definition.get("definition")
                if not isinstance(definition_text, str) or not definition_text.strip():
                    continue

                parsed_definition = {"definition": definition_text.strip()}
                example = definition.get("example")
                if isinstance(example, str) and example.strip():
                    parsed_definition["example"] = example.strip()
                definitions.append(parsed_definition)

            if definitions:
                part_of_speech = meaning.get("partOfSpeech")
                meanings.append({
                    "part_of_speech": (
                        part_of_speech.strip()
                        if isinstance(part_of_speech, str) and part_of_speech.strip()
                        else "unknown"
                    ),
                    "definitions": definitions,
                })

    return {"word": normalized, "meanings": meanings}


def lookup_definitions(word: str) -> dict[str, Any]:
    normalized = normalize_word(word)
    url = API_URL.format(word=quote(normalized.lower()))
    request = Request(url, headers={"User-Agent": "word-tile-race-definition-lookup"})

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return {"word": normalized, "meanings": []}
        raise DefinitionLookupError("Definition lookup failed.") from error
    except (OSError, TimeoutError, URLError, json.JSONDecodeError) as error:
        raise DefinitionLookupError("Definition lookup failed.") from error

    return parse_definition_response(payload, normalized)
