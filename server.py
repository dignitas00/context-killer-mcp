"""
Context-Killer MCP
==================

A small MCP server that keeps heavy code generation out of Claude's context
window. Instead of having Claude write a big file line by line (which burns a
lot of tokens), it asks Gemini to write the file and saves it straight to disk.
Claude just gets a short "done" message back.

One tool: delegate_to_gemini_and_save. Runs over stdio, which is what Claude
Desktop expects.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from google import genai
from google.genai import types

# Claude talks to this server over stdout, so logs have to go to stderr -
# otherwise we'd scramble the protocol.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [context-killer] %(levelname)s: %(message)s",
)
logger = logging.getLogger("context-killer")

# Picks up GEMINI_API_KEY from a .env file if there is one.
load_dotenv()

GEMINI_MODEL = "gemini-2.5-flash"

# We want raw code on disk, not a chat reply wrapped in markdown.
SYSTEM_INSTRUCTION = (
    "You are a pure code generator. Output ONLY the raw code. "
    "No markdown formatting, no backticks, no explanations. Just the code."
)

mcp = FastMCP("context-killer-server")


def _strip_code_fences(text: str) -> str:
    """Drop ```...``` fences in case Gemini wraps the code anyway."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    lines = lines[1:]  # opening ``` (maybe with a language tag)
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]  # closing ```
    return "\n".join(lines).strip()


def _read_context_files(context_files: Optional[list[str]]) -> str:
    """Read the files Gemini should look at. A missing file is skipped, not fatal."""
    if not context_files:
        return ""

    chunks: list[str] = []
    for raw_path in context_files:
        path = Path(raw_path).expanduser()
        try:
            content = path.read_text(encoding="utf-8")
            chunks.append(f"----- FILE: {path} -----\n{content}")
            logger.info("Loaded context file: %s (%d chars)", path, len(content))
        except FileNotFoundError:
            logger.warning("Context file not found, skipping: %s", path)
            chunks.append(f"----- FILE: {path} (NOT FOUND — skipped) -----")
        except Exception as exc:
            logger.warning("Could not read context file %s: %s", path, exc)
            chunks.append(f"----- FILE: {path} (UNREADABLE: {exc}) -----")
    return "\n\n".join(chunks)


@mcp.tool()
def delegate_to_gemini_and_save(
    task_prompt: str,
    target_file_path: str,
    context_files: Optional[list[str]] = None,
) -> str:
    """Ask Gemini to write some code and save it straight to a file.

    Handy for big or boilerplate-y files you don't want filling up the
    conversation. Gemini writes the file; you just get a short receipt back.

    Args:
        task_prompt: What to build, in plain language.
        target_file_path: Where to save it. Parent folders are created for you.
        context_files: Optional files for Gemini to read first.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        msg = (
            "ERROR: GEMINI_API_KEY is not set. Add it to your environment or a "
            ".env file (see .env.example) before calling this tool."
        )
        logger.error(msg)
        return msg

    if not task_prompt or not task_prompt.strip():
        return "ERROR: task_prompt is empty. Nothing to generate."

    # Build the prompt: the task itself, plus any files we were told to read.
    context_blob = _read_context_files(context_files)
    prompt_parts = [task_prompt.strip()]
    if context_blob:
        prompt_parts.append(
            "\n\n# Existing files for context (do not repeat them verbatim "
            "unless asked):\n" + context_blob
        )
    full_prompt = "\n".join(prompt_parts)

    # Ask Gemini.
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
            ),
        )
    except Exception as exc:
        logger.exception("Gemini API call failed")
        return f"ERROR: Gemini API call failed: {exc}"

    # Pull out the text (this can raise if the response got blocked).
    try:
        generated_code = (response.text or "").strip()
    except Exception as exc:
        logger.exception("Could not read text from Gemini response")
        return f"ERROR: Could not extract text from Gemini response: {exc}"

    if not generated_code:
        return (
            "ERROR: Gemini returned an empty response (possibly blocked by a "
            "safety filter). Nothing was written."
        )

    generated_code = _strip_code_fences(generated_code)
    if not generated_code.endswith("\n"):
        generated_code += "\n"

    # Save it, creating any missing folders along the way.
    try:
        target = Path(target_file_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated_code, encoding="utf-8")
    except Exception as exc:
        logger.exception("Failed to write generated code to disk")
        return f"ERROR: Failed to write to '{target_file_path}': {exc}"

    char_count = len(generated_code)
    line_count = generated_code.count("\n")
    logger.info("Wrote %d chars (%d lines) to %s", char_count, line_count, target)

    # The whole point: a tiny receipt instead of the full file.
    return (
        f"SUCCESS: Ghost-Context bypass complete. Gemini generated the code and "
        f"saved it directly to '{target_file_path}'. "
        f"Zero code tokens added to current context. "
        f"({line_count} lines, {char_count} chars written.)"
    )


if __name__ == "__main__":
    mcp.run()
