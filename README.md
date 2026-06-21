# Context-Killer MCP

A little MCP server that keeps big code generation out of Claude's context window.

When Claude writes a large file, every line flows back through the conversation and
eats tokens. This server hands the job to Google's Gemini instead: Gemini writes the
file straight to disk, and Claude only gets back a one-line "done". The code never
lands in the chat.

It's a single tool, `delegate_to_gemini_and_save`. You give it a prompt and a path;
it optionally reads a few files for context, asks Gemini for the code, and saves it.

> Only use this for small taks or if you just want to try it out its not fully polished
> and claude doesnt see the results which is good for saving Tokens but it may lead to
> Errors since gemini api is not as good in coding and should only be used for small simple Tasks.

## The tool

`delegate_to_gemini_and_save(task_prompt, target_file_path, context_files=None)`

- `task_prompt` – what you want built, in plain words
- `target_file_path` – where to save it (missing folders are created)
- `context_files` – optional list of files for Gemini to read first

## Setup

You'll need Python 3.11+ and a free Gemini key from
<https://aistudio.google.com/app/apikey>.

```bash
pip install -r requirements.txt
cp .env.example .env      # then paste your key into .env
```

## Use it in Claude Desktop

Add this to your `claude_desktop_config.json`:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "context-killer": {
      "command": "python",
      "args": ["C:\\path\\to\\context-killer-mcp\\server.py"],
      "env": { "GEMINI_API_KEY": "your-key-here" }
    }
  }
}
```

Restart Claude, then just ask: *"Use context-killer to write … and save it to …"*.

## Good to know

- It writes (and overwrites) files on disk, so glance at what Claude's about to do
  before approving.
- Your prompt and any context files get sent to Gemini — don't point it at secrets.
- `.env` is git-ignored. Never commit your real key.

## License

MIT — see [LICENSE](LICENSE).
