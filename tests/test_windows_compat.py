"""Regressões de compatibilidade com o Windows.

Cada classe cobre uma correção: comandos prontos sem o `python3` da Microsoft Store,
instaladores por sistema, launcher do Playwright sem `cmd.exe`, BOM do Bloco de Notas,
troca de arquivo com outro processo segurando o destino, servidor de fundo fora do
job de quem chamou, aspas no caminho do ffmpeg e nomes reservados do Windows. Os
testes que dependem do próprio Windows (PowerShell, `.cmd`) pulam nos outros sistemas;
os demais simulam `os.name` para valer em qualquer máquina.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _isolation  # noqa: F401  (efeito de import: define GB_HOME)
from _paths import ROOT

from getbrolls import browser, config, guidance, instagram_pairs, media, models, serve
from getbrolls.brief import _cli_prefix
from getbrolls.ledger import Ledger
from getbrolls.review import import_review

POWERSHELL = shutil.which("powershell") or shutil.which("pwsh") or ""
BASH = shutil.which("bash") or ""
NODE = shutil.which("node") or ""
skip_unless_windows = unittest.skipUnless(os.name == "nt", "comportamento exclusivo do Windows")


def system(module, name):
    """Troca só o `os` que `module` enxerga por um com `name` diferente; pathlib segue real."""
    return mock.patch.object(module, "os", SimpleNamespace(**{**vars(os), "name": name}))


class PythonCommandTests(unittest.TestCase):
    def test_windows_commands_use_python_not_the_store_python3(self):
        with system(config, "nt"):
            self.assertEqual("python", config.python_command())
            command = guidance.command_for("preview", "/p", "local:a")
            prefix = _cli_prefix()
        self.assertEqual("python", shlex.split(command)[0])
        self.assertTrue(prefix.startswith('python "'), prefix)

    def test_macos_and_linux_keep_python3(self):
        with system(config, "posix"):
            self.assertEqual("python3", config.python_command())
            self.assertEqual("python3", shlex.split(guidance.command_for("preview", "/p", "local:a"))[0])

    def test_media_hint_names_the_interpreter_of_this_system(self):
        with (
            mock.patch.object(media.subprocess, "run", side_effect=FileNotFoundError("ffmpeg")),
            self.assertRaises(ValueError) as raised,
        ):
            media.run(["ffmpeg", "-version"])
        self.assertIn(f"{config.python_command()} scripts/gb.py doctor", str(raised.exception))


class InstallerHintTests(unittest.TestCase):
    def test_windows_hint_puts_install_ps1_first_and_keeps_both(self):
        with system(config, "nt"):
            hint = config.installer_command(Path("C:/skill"))
        self.assertTrue(hint.startswith("powershell -ExecutionPolicy Bypass -File "), hint)
        self.assertLess(hint.index("install.ps1"), hint.index("install.sh"))

    def test_posix_hint_puts_install_sh_first_and_keeps_both(self):
        with system(config, "posix"):
            hint = config.installer_command()
        self.assertTrue(hint.startswith("bash scripts/install.sh"), hint)
        self.assertIn("install.ps1", hint)


@unittest.skipUnless(BASH, "bash ausente")
class InstallShGuardTests(unittest.TestCase):
    """`install.sh` no Git Bash para antes de achar o `python3` da Store e apontar `.venv/bin`."""

    def _run_with_uname(self, system):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "uname"
            fake.write_text(f"#!/bin/sh\nprintf '%s\\n' '{system}'\n", encoding="utf-8", newline="\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ.get("PATH", ""))
            return subprocess.run(
                [BASH, str(ROOT / "scripts" / "install.sh"), "--check"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )

    def test_git_bash_is_redirected_to_install_ps1(self):
        done = self._run_with_uname("MINGW64_NT-10.0-26200")
        self.assertEqual(2, done.returncode, done.stdout + done.stderr)
        self.assertIn("install.ps1", done.stderr)
        self.assertIn("-Check", done.stderr)
        self.assertNotIn("MISSING", done.stdout)

    def test_linux_is_not_redirected(self):
        done = self._run_with_uname("Linux")
        self.assertNotIn("Windows detectado", done.stdout + done.stderr)


class PowerShellScriptEncodingTests(unittest.TestCase):
    def test_every_non_ascii_powershell_script_has_a_utf8_bom(self):
        # Sem BOM, o Windows PowerShell 5.1 lê o .ps1 na página de código ANSI e
        # mostra "cÃ³digo" no lugar de "código".
        for path in sorted((ROOT / "scripts").glob("*.ps1")):
            data = path.read_bytes()
            if any(byte > 127 for byte in data):  # noqa: PLR2004 - ASCII range
                self.assertTrue(data.startswith(b"\xef\xbb\xbf"), f"{path.name} sem BOM")

    def test_installer_probes_python_and_falls_back_to_the_launcher(self):
        script = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("function Test-PythonCandidate", script)
        self.assertIn("'py'", script)
        for version in ("-3.13", "-3.12", "-3.11"):
            self.assertIn(version, script)
        self.assertNotIn("-File 'python' -Arguments", script)


@skip_unless_windows
@unittest.skipUnless(POWERSHELL, "PowerShell ausente")
class InstallPs1PythonDiscoveryTests(unittest.TestCase):
    """O `-Check` executa cada candidato: um `python` que só sai com 9009 não conta."""

    def _check(self, python_cmd_body):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "python.cmd").write_text(python_cmd_body, encoding="ascii")
            system32 = str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
            env = dict(os.environ, PATH=tmp + os.pathsep + system32)
            return subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT / "scripts" / "install.ps1"),
                    "-Check",
                ],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=120,
            )

    def test_store_stub_lookalike_is_reported_missing(self):
        stub = (
            "@echo Python was not found; run without arguments to install from the Microsoft Store\r\n@exit /b 9009\r\n"
        )
        done = self._check(stub)
        self.assertIn("MISSING: python", done.stdout)

    def test_working_python_is_accepted(self):
        done = self._check(f'@"{sys.executable}" %*\r\n')
        self.assertNotIn("MISSING: python", done.stdout)
        self.assertIn("python.cmd", done.stdout)


@skip_unless_windows
@unittest.skipUnless(POWERSHELL and NODE, "PowerShell e Node necessários")
class PlaywrightLauncherTests(unittest.TestCase):
    """O launcher roda o `.js` com node.exe: `&` na URL chega inteiro ao Playwright CLI."""

    def test_ampersand_in_url_reaches_the_cli_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts" / "playwright.ps1", root / "scripts" / "playwright.ps1")
            entry = root / ".tools" / "node_modules" / "@playwright" / "cli" / "playwright-cli.js"
            entry.parent.mkdir(parents=True)
            entry.write_text("console.log(JSON.stringify(process.argv.slice(2)));\n", encoding="utf-8")
            url = "https://example.com/watch?a=1&b=2"
            done = subprocess.run(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "scripts" / "playwright.ps1"),
                    "-s=gb-test",
                    "open",
                    url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["-s=gb-test", "open", url], json.loads(done.stdout.strip().splitlines()[-1]))


class BrowserPlanPrefixTests(unittest.TestCase):
    def _tree(self, tmp, *, entry=False, posix_bin=False):
        root = Path(tmp)
        modules = root / ".tools" / "node_modules"
        if entry:
            path = modules / "@playwright" / "cli" / "playwright-cli.js"
            path.parent.mkdir(parents=True)
            path.write_text("", encoding="utf-8")
        if posix_bin:
            path = modules / ".bin" / "playwright-cli"
            path.parent.mkdir(parents=True)
            path.write_text("", encoding="utf-8")
        return root

    def test_windows_uses_the_powershell_launcher_when_installed(self):
        with tempfile.TemporaryDirectory() as tmp, system(browser, "nt"):
            prefix = browser.cli_prefix(self._tree(tmp, entry=True))
        self.assertEqual("powershell", prefix[0])
        self.assertIn("Bypass", prefix)
        self.assertTrue(prefix[-1].endswith("playwright.ps1"), prefix)

    def test_posix_uses_the_bash_launcher_when_installed(self):
        with tempfile.TemporaryDirectory() as tmp, system(browser, "posix"):
            prefix = browser.cli_prefix(self._tree(tmp, posix_bin=True))
        self.assertEqual("bash", prefix[0])
        self.assertTrue(prefix[-1].endswith("playwright.sh"), prefix)

    def test_without_local_install_the_previous_npx_route_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = browser.cli_prefix(self._tree(tmp))
        self.assertEqual(["npx", "--yes", "--package", "@playwright/cli", "playwright-cli"], prefix)


class ByteOrderMarkTests(unittest.TestCase):
    def test_env_file_saved_with_bom_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_bytes(b"\xef\xbb\xbfGB_GIF_FPS=7\r\n")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GB_GIF_FPS", None)
                config.load_env(env_file)
                self.assertEqual("7", os.environ["GB_GIF_FPS"])

    def test_review_json_saved_with_bom_reaches_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"type": "outro"}).encode("utf-8"))
            with self.assertRaises(ValueError) as raised:
                import_review(Ledger(tmp), str(path), "Ana")
        self.assertNotIsInstance(raised.exception, json.JSONDecodeError)
        self.assertIn("outra coleta", str(raised.exception))


class ReplaceFileTests(unittest.TestCase):
    @staticmethod
    def _sharing_violation():
        error = PermissionError(13, "O arquivo já está sendo usado por outro processo")
        error.winerror = 32  # pyright: ignore[reportAttributeAccessIssue]
        return error

    def test_windows_retries_while_another_process_holds_the_target(self):
        calls = []

        def flaky(self, target):
            calls.append(target)
            if len(calls) < 3:  # noqa: PLR2004 - two failures, then success
                raise ReplaceFileTests._sharing_violation()
            return target

        sleeps = []
        with system(models, "nt"), mock.patch.object(models.Path, "replace", flaky):
            models.replace_file("a.tmp", "a", sleep=sleeps.append)
        self.assertEqual(3, len(calls))
        self.assertEqual(2, len(sleeps))

    def test_windows_gives_up_after_the_last_attempt(self):
        def always(self, target):
            raise ReplaceFileTests._sharing_violation()

        with (
            system(models, "nt"),
            mock.patch.object(models.Path, "replace", always),
            self.assertRaises(PermissionError),
        ):
            models.replace_file("a.tmp", "a", sleep=lambda _s: None)

    def test_other_errors_and_other_systems_do_not_retry(self):
        calls = []

        def denied(self, target):
            calls.append(target)
            raise PermissionError(13, "negado")

        with mock.patch.object(models.Path, "replace", denied):
            with system(models, "nt"), self.assertRaises(PermissionError):
                models.replace_file("a.tmp", "a", sleep=lambda _s: None)
            with system(models, "posix"), self.assertRaises(PermissionError):
                models.replace_file("a.tmp", "a", sleep=lambda _s: None)
        self.assertEqual(2, len(calls))

    def test_real_replace_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "x.tmp"
            target = Path(tmp) / "x"
            source.write_text("novo", encoding="utf-8")
            target.write_text("velho", encoding="utf-8")
            models.replace_file(source, target)
            self.assertEqual("novo", target.read_text(encoding="utf-8"))
            self.assertFalse(source.exists())


class BackgroundServerTests(unittest.TestCase):
    def test_windows_tries_to_leave_the_callers_job_then_falls_back(self):
        seen = []

        def popen(_command, **kwargs):
            seen.append(kwargs.get("creationflags"))
            if len(seen) == 1:
                raise OSError(5, "Acesso negado")
            return "processo"

        with system(serve, "nt"), mock.patch.object(serve.subprocess, "Popen", popen):
            self.assertEqual("processo", serve._spawn_detached(["x"]))
        self.assertEqual(
            [serve.WINDOWS_DETACHED_FLAGS | serve.WINDOWS_BREAKAWAY_FLAG, serve.WINDOWS_DETACHED_FLAGS], seen
        )

    def test_posix_keeps_a_new_session(self):
        captured = {}

        def popen(_command, **kwargs):
            captured.update(kwargs)
            return "processo"

        with system(serve, "posix"), mock.patch.object(serve.subprocess, "Popen", popen):
            serve._spawn_detached(["x"])
        self.assertTrue(captured["start_new_session"])
        self.assertNotIn("creationflags", captured)

    def test_timeout_kills_the_whole_tree_on_windows(self):
        process = mock.MagicMock()
        process.pid = 4242
        with (
            system(serve, "nt"),
            mock.patch.object(serve.subprocess, "run") as run,
        ):
            serve._kill_tree(process)
        self.assertEqual(["taskkill", "/PID", "4242", "/T", "/F"], run.call_args.args[0])
        process.terminate.assert_called_once()


class FilterPathQuoteTests(unittest.TestCase):
    def test_apostrophe_closes_escapes_and_reopens_the_quote(self):
        self.assertEqual("C\\:/a/o'\\\\\\''b/f.ttf", media._filter_path("C:\\a\\o'b\\f.ttf"))
        self.assertEqual("C\\:/Windows/Fonts/arial.ttf", media._filter_path("C:\\Windows\\Fonts\\arial.ttf"))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_ffmpeg_draws_with_a_font_under_an_apostrophe_folder(self):
        font = next((Path(f) for f in media.DEFAULT_FONTS if Path(f).is_file()), None)
        if font is None or not media.drawtext_available():
            self.skipTest("sem fonte ou sem drawtext")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "O'Brien"
            folder.mkdir()
            copy = folder / font.name
            shutil.copy2(font, copy)
            out = Path(tmp) / "out.png"
            done = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=64x64:d=0.1",
                    "-vf",
                    f"drawtext=fontfile='{media._filter_path(copy)}':text='1':fontsize=20:fontcolor=white",
                    "-frames:v",
                    "1",
                    "-y",
                    str(out),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertTrue(out.is_file())


class ReservedStemTests(unittest.TestCase):
    def test_windows_rejects_device_names(self):
        with system(instagram_pairs, "nt"):
            for stem in ("CON", "nul", "com1.clip", "LPT9"):
                self.assertTrue(instagram_pairs.unsafe_stem(stem), stem)
            for stem in ("creator_01_ABC", "console", "CONTENT", "con_01_X"):
                self.assertFalse(instagram_pairs.unsafe_stem(stem), stem)

    def test_other_systems_keep_the_previous_rule(self):
        with system(instagram_pairs, "posix"):
            self.assertFalse(instagram_pairs.unsafe_stem("CON"))
            self.assertTrue(instagram_pairs.unsafe_stem(".hidden"))
            self.assertTrue(instagram_pairs.unsafe_stem("a..b"))


class StandaloneCollectorOutputTests(unittest.TestCase):
    def test_help_is_utf8_even_when_piped(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "getbrolls" / "instagram_pairs.py"), "--help"],
            capture_output=True,
            env=env,
            check=False,
            timeout=60,
        )
        self.assertEqual(0, done.returncode, done.stderr)
        text = done.stdout.decode("utf-8")  # estrito: cp1252 quebraria aqui
        self.assertTrue(any(ord(ch) > 127 for ch in text), "a ajuda deveria ter acentos")  # noqa: PLR2004


class YouTubeHelperRuntimeTests(unittest.TestCase):
    def test_helpers_find_the_windows_venv_yt_dlp(self):
        script = (ROOT / "scripts" / "getbrolls" / "tools" / "youtube" / "_runtime.sh").read_text(encoding="utf-8")
        self.assertIn(".venv/bin/yt-dlp", script)
        self.assertIn(".venv/Scripts/yt-dlp.exe", script)


if __name__ == "__main__":
    unittest.main()
