"""Reviewable Playwright CLI capture plan; browser interactions stay with agent."""

import os
from datetime import UTC
from pathlib import Path

from .http import public_url
from .review import project_id
from .rules import domain_matches

ROOT = Path(__file__).resolve().parents[2]


def cli_prefix(root=None):
    """Como chamar o Playwright CLI: o launcher da skill quando `.tools` tem a versão fixada.

    No Windows o launcher PowerShell roda o `playwright-cli.js` direto com node.exe, sem
    passar pelo cmd.exe (que corta URL com `&`). Sem instalação local, fica o `npx` de antes.
    """
    root = Path(root) if root is not None else ROOT
    entry = root / ".tools" / "node_modules" / "@playwright" / "cli" / "playwright-cli.js"
    if os.name == "nt":
        shim = root / ".tools" / "node_modules" / ".bin" / "playwright-cli.cmd"
        if entry.is_file() or shim.is_file():
            launcher = root / "scripts" / "playwright.ps1"
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher)]
    elif (root / ".tools" / "node_modules" / ".bin" / "playwright-cli").is_file():
        return ["bash", str(root / "scripts" / "playwright.sh")]
    return ["npx", "--yes", "--package", "@playwright/cli", "playwright-cli"]


def plan(ledger, url, rules):
    if not public_url(url):
        raise ValueError("Use uma URL pública HTTPS sem credenciais.")
    if domain_matches(url, rules["blocked_domains"]):
        raise ValueError("Domínio bloqueado pelo usuário.")
    if not any(t in rules["asset_types"] for t in ("web_screenshot", "news_screenshot")):
        raise ValueError("Screenshots desabilitados em RULES.md.")
    asset_type = "news_screenshot" if "news_screenshot" in rules["asset_types"] else "web_screenshot"
    b = rules["browser"]
    mode = b["viewport"]
    w = b[mode + "_width"]
    h = b[mode + "_height"]
    session = "gb-" + project_id(ledger)[:8]
    directory = ledger.root.parent / "output/playwright"
    directory.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    png = directory / ("capture-" + stamp + ".png")
    prefix = [*cli_prefix(), "-s=" + session]
    commands = [
        [*prefix, "open", url, "--headed"],
        [*prefix, "resize", str(w), str(h)],
        [*prefix, "snapshot"],
        prefix + ["screenshot", "--filename=" + str(png)] + (["--full-page"] if b["full_page"] else []),
    ]
    return {
        "asset_type": asset_type,
        "url": url,
        "viewport": {"width": w, "height": h, "kind": mode, "emulates_device": False},
        "output": str(png),
        "commands": commands,
        "editorial_rules": rules["editorial_rules"],
        "preferred_domains": rules["preferred_domains"],
        "instructions": [
            "Execute open/resize e leia snapshot antes de interagir.",
            "Confirme manchete, data, autor, URL e conteúdo carregado.",
            "Se necessário, interaja por refs do snapshot e tire novo snapshot.",
            "Captura não passa por paywall/login nem autentica autoria automaticamente.",
            f"Importe PNG com resolve --file --asset-type {asset_type} --source-url URL --title TITULO --captured-at ISO --shot ID.",
            "Preview, revisão humana, permit e fetch continuam obrigatórios.",
        ],
    }
