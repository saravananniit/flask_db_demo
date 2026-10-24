Here's how to run the demo with uv. Unzip `flask_realtime_demo.zip` and open a terminal in that folder.

**1. Install uv (once)**

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Create the environment and install dependencies**

```bash
uv venv
uv pip install -r requirements.txt
```

`uv venv` creates `.venv`, and `uv pip install` installs into it automatically, so you don't need to activate it first.

**3. Run the tests**

```bash
uv run python -m pytest -q
```

**4. Run the app (development)**

```bash
uv run flask --app app run --debug
```

Open http://127.0.0.1:5000 in two browser tabs, and changes in one appear in the other.

**5. Production-style run (Linux/macOS)**

```bash
export APP_ENV=production
export FLASK_SECRET_KEY="$(uv run python -c 'import secrets; print(secrets.token_hex())')"
uv run gunicorn -k gthread -w 1 --threads 16 -b 0.0.0.0:8000 wsgi:app
```

Gunicorn doesn't run on Windows. There, use the development command from step 4, or Waitress:

```bash
uv pip install waitress
uv run waitress-serve --listen=127.0.0.1:8000 wsgi:app
```

**Optional: make it a proper uv project**

If you'd rather use `uv add` and `uv sync`, run these once inside the folder:

```bash
uv init --bare
uv add "flask>=3.1,<3.2" gunicorn
uv add --dev pytest
```

After that, `uv run flask --app app run --debug` works with no manual venv step, and `uv sync` recreates the environment on any machine.