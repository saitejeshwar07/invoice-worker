"""Provider-agnostic JSON chat. Supports OpenAI and Gemini behind one interface."""
import json
import os
import re
import time
import config


def _parse(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.I | re.M).strip()

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)

        if not m:
            raise

        return json.loads(m.group(0))


class LLM:
    def __init__(self):
        self.provider = config.llm_provider()

        if self.provider == "openai":
            from openai import OpenAI

            self.client = OpenAI()
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        elif self.provider == "gemini":
            from google import genai

            self.client = genai.Client(
                api_key=os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
            )

            self.model = os.getenv(
                "GEMINI_MODEL",
                "gemini-2.5-flash"
            )

        else:
            raise RuntimeError(
                "No LLM configured. "
                "Set OPENAI_API_KEY or GEMINI_API_KEY in .env"
            )

    def _complete(self, system: str, messages: list[dict]) -> str:

        # -----------------------------
        # OpenAI
        # -----------------------------
        if self.provider == "openai":
            r = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system}
                ] + messages,
            )

            return r.choices[0].message.content or ""

        # -----------------------------
        # Gemini
        # -----------------------------
        from google.genai import types

        contents: list = []

        for m in messages:
            role = "user" if m["role"] == "user" else "model"

            if contents and contents[-1].role == role:
                contents[-1].parts.append(
                    types.Part(text=m["content"])
                )
            else:
                contents.append(
                    types.Content(
                        role=role,
                        parts=[
                            types.Part(text=m["content"])
                        ],
                    )
                )

        r = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        return r.text or ""

    def chat_json(
        self,
        system: str,
        messages: list[dict],
        retries: int = 2,
    ) -> dict:

        last = None

        # Total attempts = retries + 1
        for attempt in range(retries + 1):

            try:
                # ------------------------------------------------
                # Gemini free-tier rate-limit protection
                #
                # We wait before every LLM request so that a long
                # agent run does not exceed the requests/minute
                # limit.
                # ------------------------------------------------
                if self.provider == "gemini":
                    print(
                        "[LLM] Waiting 5 seconds before next Gemini request..."
                    )
                    time.sleep(5)

                raw = self._complete(
                    system,
                    messages
                )

            except Exception as e:

                last = e
                error_text = str(e).lower()

                # ------------------------------------------------
                # Detect temporary API failures
                # ------------------------------------------------
                transient = any(
                    x in error_text
                    for x in [
                        "503",
                        "unavailable",
                        "429",
                        "rate limit",
                        "resource exhausted",
                        "internal server error",
                        "temporarily",
                        "quota",
                    ]
                )

                if transient and attempt < retries:

                    # Longer backoff for API rate limits.
                    #
                    # attempt 0 -> 10 sec
                    # attempt 1 -> 20 sec
                    #
                    # Combined with the 5 sec request pacing above.
                    if "429" in error_text or "resource exhausted" in error_text:
                        wait_time = 10 * (attempt + 1)
                    else:
                        wait_time = 5 * (attempt + 1)

                    print(
                        f"[LLM] Temporary API error: {e}"
                    )

                    print(
                        f"[LLM] Retrying in {wait_time} seconds "
                        f"(attempt {attempt + 2}/{retries + 1})..."
                    )

                    time.sleep(wait_time)

                    continue

                # Permanent error or retries exhausted
                raise

            # ----------------------------------------------------
            # Parse JSON response
            # ----------------------------------------------------
            try:

                out = _parse(raw)

                if isinstance(out, dict):
                    return out

                raise ValueError("LLM response is not a JSON object")

            except Exception as e:

                last = e

                if attempt < retries:

                    messages = messages + [
                        {
                            "role": "assistant",
                            "content": raw,
                        },
                        {
                            "role": "user",
                            "content": (
                                "That was not a valid JSON object. "
                                "Reply with ONLY one JSON object."
                            ),
                        },
                    ]

        raise ValueError(
            f"LLM returned invalid JSON repeatedly: {last}"
        )