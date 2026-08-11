import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List

from loguru import logger
from prefect import flow, task

from src.core.logic.lattes_generators import LattesConfigGenerator, LattesListGenerator
from src.notifications.telegram import telegram_flow_state_handlers

LATTES_ID_RE = re.compile(r"(?<!\d)\d{16}(?!\d)")
DEFAULT_LATTES_PREFETCH_WORKERS = 3
LATTES_PREFETCH_ENABLED_ENV = "HORIZON_LATTES_PREFETCH"
LATTES_PREFETCH_WORKERS_ENV = "HORIZON_LATTES_DOWNLOAD_WORKERS"
LATTES_FORCE_DOWNLOAD_ENV = "HORIZON_LATTES_FORCE_DOWNLOAD"
LattesDownloader = Callable[[str, str], None]
DEFAULT_SCRIPT_WORKERS = 1
SCRIPT_WORKERS_ENV = "HORIZON_LATTES_SCRIPT_WORKERS"


class ScriptLattesRuntimeError(RuntimeError):
    """Raised when the local browser runtime cannot support scriptLattes."""


# from research_domain_lib.repository.researcher_repository import ResearcherRepository

# Mocking repository access for standalone flow execution if needed,  # but in real scenario this should inject the repo.  # For now, I'll assume we can get data.  # Since I cannot easily instantiate the real repository without DB connection in this "one-shot" agent,  # I'll create a task that *would* fetch from DB, but for now returns mock data or tries to use the repo if available.


def clean_lattes_json_output(output_dir: str) -> int:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    removed_count = 0
    for json_file in output_path.glob("*.json"):
        try:
            json_file.unlink()
            removed_count += 1
        except PermissionError:
            logger.warning(f"Could not remove stale JSON file: {json_file}")
    return removed_count


def should_skip_download_if_cached(output_dir: str, lattes_ids: List[str]) -> bool:
    if os.environ.get(LATTES_FORCE_DOWNLOAD_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    output_path = Path(output_dir)
    if not output_path.exists():
        return False
    all_exist = all((output_path / f"{lid}.json").exists() for lid in lattes_ids)
    if all_exist:
        logger.info(
            f"All {len(lattes_ids)} Lattes curricula already in {output_dir}. "
            f"Set {LATTES_FORCE_DOWNLOAD_ENV}=1 to force re-download."
        )
        return True
    missing = sum(1 for lid in lattes_ids if not (output_path / f"{lid}.json").exists())
    logger.info(
        f"{missing}/{len(lattes_ids)} Lattes curricula missing from {output_dir}, proceeding with download."
    )
    return False


def is_lattes_prefetch_enabled() -> bool:
    value = os.environ.get(LATTES_PREFETCH_ENABLED_ENV)
    if value is None:
        return True

    return value.strip().lower() not in {"0", "false", "no", "off"}


def get_lattes_prefetch_workers() -> int:
    value = os.environ.get(LATTES_PREFETCH_WORKERS_ENV)
    if not value:
        return DEFAULT_LATTES_PREFETCH_WORKERS

    try:
        workers = int(value)
    except ValueError as exc:
        raise ValueError(f"{LATTES_PREFETCH_WORKERS_ENV} must be an integer") from exc

    if workers < 1:
        raise ValueError(f"{LATTES_PREFETCH_WORKERS_ENV} must be >= 1")

    return workers


def get_script_workers() -> int:
    value = os.environ.get(SCRIPT_WORKERS_ENV)
    if not value:
        return DEFAULT_SCRIPT_WORKERS
    try:
        workers = int(value)
    except ValueError as exc:
        raise ValueError(f"{SCRIPT_WORKERS_ENV} must be an integer") from exc
    if workers < 1:
        raise ValueError(f"{SCRIPT_WORKERS_ENV} must be >= 1")
    return workers


def collect_lattes_ids_from_list(list_path: str) -> List[str]:
    ids = []
    for line in Path(list_path).read_text().splitlines():
        match = LATTES_ID_RE.search(line)
        if match:
            ids.append(match.group(0))
    return ids


def _check_playwright_chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def _read_command_version(command: List[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, check=False, text=True)
    except OSError:
        return ""

    return "\n".join(part for part in [result.stdout, result.stderr] if part)


def _major_version(version_output: str) -> str:
    match = re.search(r"\b(\d{2,3})\.\d+", version_output)
    return match.group(1) if match else ""


def _candidate_chrome_binaries(chrome_binary: str | None = None) -> List[str]:
    candidates = []
    if chrome_binary:
        candidates.append(chrome_binary)

    env_binary = os.environ.get("CHROME_BINARY")
    if env_binary and env_binary not in candidates:
        candidates.append(env_binary)

    for command in [
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "chromium",
        "chromium-browser",
    ]:
        path = shutil.which(command)
        if path and path not in candidates:
            candidates.append(path)

    return candidates


def validate_script_lattes_runtime(
    chromedriver_path: str = "./chromedriver", chrome_binary: str | None = None
) -> str:
    """Validate that Playwright Chromium is available for scriptLattes."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError as exc:
        raise ScriptLattesRuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    if not _check_playwright_chromium():
        raise ScriptLattesRuntimeError(
            "Playwright Chromium is not installed. Run: playwright install chromium"
        )

    return "playwright-chromium"


LATTES_RECAPTCHA_SITE_KEY = "6Le8-aQUAAAAAEh7lq-D8bscahYZDZ4RKXBEhiov"
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
window.chrome = { runtime: {} };
"""


def _patch_script_lattes_browser() -> None:
    import scriptLattes.baixaLattes as baixa_lattes

    original = baixa_lattes.LattesRobot.create_browser
    if getattr(original, "_horizon_browser_patched", False):
        return

    patch_logger = logger.bind(patch="create_browser")

    def patched_create_browser(self):
        if baixa_lattes.sync_playwright is None:
            raise ImportError("Playwright is not installed.")
        self.playwright = baixa_lattes.sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
            user_agent=user_agent,
        )
        self.page = self.context.new_page()
        self.page.add_init_script(STEALTH_INIT_SCRIPT)
        patch_logger.debug("Browser created with stealth patches")

    patched_create_browser._horizon_browser_patched = True
    baixa_lattes.LattesRobot.create_browser = patched_create_browser

    original_get_lids = baixa_lattes.LattesRobot._get_lids_10_16
    if not getattr(original_get_lids, "_horizon_get_lids_patched", False):

        def patched_get_lids_10_16(self, lid):
            lids = {10: "", 16: ""}
            if len(lid) == 10:
                lids[10] = lid
            if len(lid) == 16:
                lids[16] = lid
                self.page.goto(
                    baixa_lattes.URL_LATTES_ID16.format(lid),
                    wait_until="domcontentloaded",
                )
                current_url = self.page.url
                parsed = baixa_lattes.urllib.parse.urlparse(current_url)
                query_params = baixa_lattes.urllib.parse.parse_qs(parsed.query)
                if "id" in query_params:
                    lid10 = query_params["id"][0]
                    if len(lid10) == 10:
                        lids[10] = lid10
            return lids

        patched_get_lids_10_16._horizon_get_lids_patched = True
        baixa_lattes.LattesRobot._get_lids_10_16 = patched_get_lids_10_16


def _wait_grecaptcha_ready(page, timeout: float = 20.0) -> bool:
    """Wait for grecaptcha.execute to become available (async defer loaded)."""
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        ready = page.evaluate(
            "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'"
        )
        if ready:
            return True
        page.wait_for_timeout(1000)
    return False


def _exec_grecaptcha_v3(page, site_key: str) -> str:
    """Execute reCAPTCHA v3 and return the token string."""
    return page.evaluate(
        """
        async (key) => {
            try {
                const t = await grecaptcha.execute(key, {action: 'id_form_previw'});
                return typeof t === 'string' ? t : '';
            } catch(e) {
                return '';
            }
        }
    """,
        site_key,
    )


def _patch_script_lattes_execute_js() -> None:
    import scriptLattes.baixaLattes as baixa_lattes

    original = baixa_lattes.LattesRobot._execute_js
    if getattr(original, "_horizon_exec_patched", False):
        return

    URL_LATTES_ID10 = baixa_lattes.URL_LATTES_ID10
    exec_logger = logger.bind(patch="_execute_js")

    def patched_execute_js(self, lids):
        if not lids[10]:
            return

        lids_id = lids[10]
        exec_logger.debug(f"Navigating to preview page for ID {lids_id}")
        self.page.goto(baixa_lattes.URL.format(lids_id), wait_until="domcontentloaded")
        self.page.wait_for_timeout(200)
        self.page.set_default_timeout(30000)

        has_recaptcha = self.page.evaluate(
            "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'"
        )
        page_content = self.page.content()
        grecaptcha_in_html = "grecaptcha" in page_content

        if has_recaptcha or grecaptcha_in_html:
            if not has_recaptcha:
                exec_logger.info("grecaptcha in HTML but not loaded yet, waiting...")
                if not _wait_grecaptcha_ready(self.page):
                    exec_logger.error(
                        f"grecaptcha did not load for {lids_id}, skipping"
                    )
                    return

            exec_logger.info(f"New Lattes format (reCAPTCHA v3) for ID {lids_id}")
            try:
                token = _exec_grecaptcha_v3(self.page, LATTES_RECAPTCHA_SITE_KEY)
                if not token:
                    exec_logger.warning("Empty token on first attempt, retrying...")
                    self.page.wait_for_timeout(500)
                    token = _exec_grecaptcha_v3(self.page, LATTES_RECAPTCHA_SITE_KEY)
            except Exception as exc:
                exec_logger.warning(f"reCAPTCHA execution failed for {lids_id}: {exc}")
                token = ""

            if not token:
                exec_logger.error(
                    f"Could not obtain reCAPTCHA token for {lids_id}, skipping"
                )
                return

            exec_logger.debug(f"reCAPTCHA token obtained ({len(token)} chars)")
            cv_url = (
                URL_LATTES_ID10.format(lids_id)
                + "&idiomaExibicao=1&tokenCaptchar="
                + token
            )
            self.page.goto(cv_url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(500)
        else:
            exec_logger.debug(f"Old Lattes format (abreCV) for ID {lids_id}")
            cmd_open_cv = "abreCV()"
            self.page.evaluate(cmd_open_cv)

            for delay in [1, 1, 2, 2, 2]:
                self.page.wait_for_timeout(delay * 1000)
                pages = self.context.pages
                if len(pages) > 1:
                    self.page = pages[-1]
                    self.page.wait_for_load_state("networkidle")
                    break

        if not lids[16]:
            page_content = self.page.content()
            lids[16] = self._extract_lid16(page_content)
            if self.lid_type == 16 and len(lids[16]) != 16:
                exec_logger.warning(
                    f"Could not extract 16-digit ID for {lids_id}, skipping"
                )
                return

        self.store_html(lids[self.lid_type], self.page.content())
        exec_logger.info(f"Stored HTML for ID {lids_id}")

    patched_execute_js._horizon_exec_patched = True
    baixa_lattes.LattesRobot._execute_js = patched_execute_js


def patch_script_lattes_runtime(chrome_binary: str | None = None) -> None:
    try:
        import scriptLattes.baixaLattes as baixa_lattes
    except ImportError as exc:
        raise ScriptLattesRuntimeError("scriptLattes is not installed.") from exc

    if getattr(baixa_lattes, "_horizon_runtime_patched", False):
        return

    _patch_script_lattes_browser()
    _patch_script_lattes_execute_js()

    def get_data(id_lattes, diretorio):
        rob = baixa_lattes.LattesRobot(results_dir=diretorio)
        print(
            f"Baixando CV Lattes: {id_lattes}. "
            "Este processo pode demorar alguns segundos."
        )
        rob.load_codes(id_lattes)
        rob.check_downloaded_cvs()

        try:
            rob.create_browser()
            rob.collect_html_cvs(0, None)
        finally:
            if getattr(rob, "browser", None):
                rob.browser.close()
            if getattr(rob, "playwright", None):
                rob.playwright.stop()

    baixa_lattes.__get_data = get_data
    baixa_lattes._horizon_runtime_patched = True


def _script_lattes_downloader(lattes_id: str, cache_dir: str) -> None:
    import scriptLattes.baixaLattes as baixa_lattes

    baixa_lattes.baixaCVLattes(lattes_id, cache_dir)


def _is_rate_limited(path: Path) -> bool:
    """Check if a cached file is a rate-limit response (429)."""
    if not path.exists():
        return True
    if path.stat().st_size < 2000:
        with open(path) as f:
            content = f.read(200)
        if "429 Too Many Requests" in content:
            return True
    return False


def _batch_script_lattes_downloader(
    lattes_ids: List[str],
    cache_dir: str,
    max_retries: int = 3,
) -> List[str]:
    """Download multiple Lattes CVs in a single browser session.

    Avoids the ~2s browser creation/destruction overhead per ID.
    Retries rate-limited IDs with exponential backoff.
    Returns the list of IDs that were successfully downloaded.
    """
    import scriptLattes.baixaLattes as baixa_lattes

    batch_logger = logger.bind(batch="batch_download")
    rate_limit_backoff = 1.0

    # Phase 1: initial bulk download
    rob = baixa_lattes.LattesRobot(results_dir=cache_dir)
    for lid in lattes_ids:
        rob.load_codes(lid)
    rob.check_downloaded_cvs()

    try:
        rob.create_browser()
        rob.collect_html_cvs(0, None)
    finally:
        if getattr(rob, "browser", None):
            rob.browser.close()
        if getattr(rob, "playwright", None):
            rob.playwright.stop()

    # Phase 2: retry rate-limited IDs
    retry_ids = [lid for lid in lattes_ids if _is_rate_limited(Path(cache_dir) / lid)]

    for attempt in range(max_retries):
        if not retry_ids:
            break

        wait = rate_limit_backoff * (2**attempt)
        batch_logger.warning(
            f"Rate-limited {len(retry_ids)} IDs, "
            f"retrying in {wait:.0f}s (attempt {attempt + 1}/{max_retries})"
        )
        time.sleep(wait)

        # Remove stale 429 files so check_downloaded_cvs won't skip them
        for lid in retry_ids:
            cached_file = Path(cache_dir) / lid
            if cached_file.exists():
                cached_file.unlink()

        rob = baixa_lattes.LattesRobot(results_dir=cache_dir)
        for lid in retry_ids:
            rob.load_codes(lid)
        rob.check_downloaded_cvs()

        try:
            rob.create_browser()
            rob.collect_html_cvs(0, None)
        finally:
            if getattr(rob, "browser", None):
                rob.browser.close()
            if getattr(rob, "playwright", None):
                rob.playwright.stop()

        still_limited = [
            lid for lid in retry_ids if _is_rate_limited(Path(cache_dir) / lid)
        ]
        if len(still_limited) >= len(retry_ids) * 0.5:
            rate_limit_backoff *= 2
        retry_ids = still_limited

    if retry_ids:
        batch_logger.warning(
            f"Giving up on {len(retry_ids)} rate-limited IDs after "
            f"{max_retries} retries"
        )

    # Phase 3: collect results
    successful = []
    for lid in lattes_ids:
        cached_file = Path(cache_dir) / lid
        if cached_file.exists() and not _is_rate_limited(cached_file):
            successful.append(lid)
            batch_logger.debug(
                f"Downloaded {lid} ({cached_file.stat().st_size:,} bytes)"
            )

    return successful


def _download_lattes_to_cache(
    lattes_id: str, cache_dir: str, downloader: LattesDownloader
) -> None:
    downloader(lattes_id, cache_dir)

    cached_file = Path(cache_dir) / lattes_id
    if not cached_file.exists():
        raise ScriptLattesRuntimeError(
            f"scriptLattes did not create the cache file for Lattes ID {lattes_id}"
        )


def prefetch_lattes_cache(
    lattes_ids: List[str],
    cache_dir: str,
    max_workers: int = DEFAULT_LATTES_PREFETCH_WORKERS,
    downloader: LattesDownloader | None = None,
) -> List[str]:
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    seen_ids = set()
    missing_ids = []
    for lattes_id in lattes_ids:
        if lattes_id in seen_ids:
            continue
        seen_ids.add(lattes_id)

        if not (cache_path / lattes_id).exists():
            missing_ids.append(lattes_id)

    if not missing_ids:
        logger.info(f"All {len(seen_ids)} Lattes curricula are already cached.")
        return []

    patch_script_lattes_runtime()

    if downloader is None:
        return _batch_prefetch(missing_ids, str(cache_path), max_workers)

    worker_count = min(max_workers, len(missing_ids))
    logger.info(
        f"Prefetching {len(missing_ids)} missing Lattes curricula into "
        f"{cache_dir} with {worker_count} worker(s) (legacy per-ID mode)."
    )

    if worker_count == 1:
        failed_ids = []
        for lattes_id in missing_ids:
            try:
                _download_lattes_to_cache(lattes_id, str(cache_path), downloader)
            except Exception as exc:
                logger.warning(
                    f"Failed to download Lattes {lattes_id}, skipping: {exc}"
                )
                failed_ids.append(lattes_id)
        if failed_ids:
            logger.warning(
                f"Skipped {len(failed_ids)} curricula due to download errors: {failed_ids}"
            )
        return [lid for lid in missing_ids if lid not in failed_ids]

    failed_ids = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _download_lattes_to_cache, lattes_id, str(cache_path), downloader
            ): lattes_id
            for lattes_id in missing_ids
        }
        for future in as_completed(futures):
            lattes_id = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.warning(
                    f"Failed to download Lattes {lattes_id}, skipping: {exc}"
                )
                failed_ids.append(lattes_id)

    if failed_ids:
        logger.warning(
            f"Skipped {len(failed_ids)} curricula due to download errors: {failed_ids}"
        )

    return [lid for lid in missing_ids if lid not in failed_ids]


def _batch_prefetch(
    missing_ids: List[str], cache_dir: str, max_workers: int
) -> List[str]:
    """Download all missing IDs using batch mode (one browser per worker chunk)."""
    n_workers = min(max_workers, len(missing_ids))
    all_successful = []
    all_failed = []

    logger.info(
        f"Batch-prefetching {len(missing_ids)} curricula into "
        f"{cache_dir} with {n_workers} browser(s)."
    )

    if n_workers <= 1:
        successful = _batch_script_lattes_downloader(missing_ids, cache_dir)
        if len(successful) != len(missing_ids):
            all_failed = [lid for lid in missing_ids if lid not in successful]
            logger.warning(
                f"Skipped {len(all_failed)} curricula due to download errors: {all_failed}"
            )
        return successful

    chunks = []
    chunk_size = (len(missing_ids) + n_workers - 1) // n_workers
    for i in range(0, len(missing_ids), chunk_size):
        chunks.append(missing_ids[i : i + chunk_size])

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(_batch_script_lattes_downloader, chunk, cache_dir): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            chunk_idx = futures[future]
            try:
                successful = future.result()
                all_successful.extend(successful)
                chunk_failed = [
                    lid for lid in chunks[chunk_idx] if lid not in successful
                ]
                all_failed.extend(chunk_failed)
            except Exception as exc:
                logger.warning(f"Batch chunk {chunk_idx} failed: {exc}")
                all_failed.extend(chunks[chunk_idx])

    if all_failed:
        logger.warning(
            f"Skipped {len(all_failed)} curricula due to download errors: {all_failed}"
        )

    return [lid for lid in missing_ids if lid not in all_failed]


@task
def get_researchers_from_db() -> List[Dict]:
    import zipfile

    from research_domain.controllers import ResearcherController

    ctrl = ResearcherController()
    researchers = ctrl.get_all()

    seen_ids: set = set()
    result: List[Dict] = []
    for r in researchers:
        lattes_id = str(getattr(r, "brand_id", "") or "")
        if not lattes_id or not LATTES_ID_RE.fullmatch(lattes_id):
            cnpq_url = str(getattr(r, "cnpq_url", "") or "")
            match = LATTES_ID_RE.search(cnpq_url)
            if match:
                lattes_id = match.group(0)

        if (
            lattes_id
            and LATTES_ID_RE.fullmatch(lattes_id)
            and lattes_id not in seen_ids
        ):
            seen_ids.add(lattes_id)
            result.append({"name": r.name, "lattes_id": lattes_id})
    
    # Lattes profiles of administrative staff
    result.extend(
        [
            {"name": "Eglalciane de Lyrio tongo Castro", "lattes_id": "1286695973576604"},
            {"name": "Marcelo Franco de Almeida", "lattes_id": "3326528545654268"},
            {"name": "Geruza Ferreira Martins", "lattes_id": "8819106413417445"},
            {"name": "Emerson Atilio Birchler", "lattes_id": "6630084362240387"},
            {"name": "Sâmela Pedrada Cardoso", "lattes_id": "4586755132358194"},
            {"name": "Dárcio Leitão Quintas", "lattes_id": "8017989819517663"},
            {"name": "Elika Capucho Delazare", "lattes_id": "1989148534910367"},
            {"name": "Wagner Scopel Falcão", "lattes_id": "2924845095994521"},
        ]
    )

    if len(result) < 20:
        export_path = "data/exports/exports_canonical.zip"
        if os.path.exists(export_path):
            try:
                with zipfile.ZipFile(export_path) as z:
                    with z.open("researchers_canonical.json") as f:
                        historical = json.load(f)
                for r in historical:
                    cnpq_url = str(r.get("cnpq_url") or "")
                    match = LATTES_ID_RE.search(cnpq_url)
                    if match and match.group(0) not in seen_ids:
                        seen_ids.add(match.group(0))
                        result.append({"name": r["name"], "lattes_id": match.group(0)})
            except Exception as e:
                logger.warning(f"Historical export fallback failed: {e}")

    logger.info(f"Found {len(result)} researchers with valid Lattes IDs.")
    return result


@task
def generate_config(output_dir: str, list_path: str, cache_dir: str) -> str:
    config_gen = LattesConfigGenerator()
    config_path = os.path.abspath("cache/lattes.config")
    config_gen.generate(config_path, output_dir, list_path, cache_dir=cache_dir)
    return config_path


@task
def generate_list(researchers: List[Dict]) -> str:
    list_gen = LattesListGenerator()
    list_path = os.path.abspath("cache/lattes.list")
    list_gen.generate_from_db(list_path, researchers)
    return list_path


def _patch_grupo_carregar_parallel(max_workers: int) -> None:
    from scriptLattes.grupo import Grupo

    original = Grupo.carregarDadosCVLattes

    if getattr(original, "_horizon_parallel_patched", False):
        return

    def patched_carregar(self):
        cache_dir = self.diretorioCache
        missing = [
            m.idLattes
            for m in self.listaDeMembros
            if not Path(cache_dir, m.idLattes).exists()
        ]
        if missing:
            logger.warning(
                f"{len(missing)} cached files missing — "
                f"falling back to sequential parsing: {missing}"
            )
            original(self)
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(membro.carregarDadosCVLattes): membro
                for membro in self.listaDeMembros
            }
            indice = 1
            total = len(futures)
            for future in as_completed(futures):
                membro = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    logger.error(
                        f"Failed to process Lattes ID {membro.idLattes}: {exc}"
                    )
                    raise
                membro.filtrarItemsPorPeriodoOuTermos()
                print(f"\n[LENDO REGISTRO LATTES: {indice}o. DE {total}]")
                indice += 1
                print(membro)

    patched_carregar._horizon_parallel_patched = True
    Grupo.carregarDadosCVLattes = patched_carregar


@task
def run_script_lattes_real(config_path: str):
    try:
        from scriptLattes.run import executar_scriptLattes

        patch_script_lattes_runtime()
        logger.info(f"Starting real scriptLattes execution with config: {config_path}")

        n_workers = get_script_workers()
        if n_workers > 1:
            _patch_grupo_carregar_parallel(n_workers)

        executar_scriptLattes(config_path, somente_json=True)
        logger.info("Real scriptLattes execution finished.")
    except ImportError:
        logger.error("scriptLattes library not found. Please install it.")
        raise
    except Exception as e:
        logger.error(f"scriptLattes execution failed: {e}")
        raise


def _clean_stale_json_files(output_dir: str, valid_ids: set) -> None:
    """Remove JSON files whose Lattes ID is not in the current valid set.

    Filenames follow the pattern ``*_<id>.json`` where the last underscore-
    separated token (before ``.json``) is the 16-digit Lattes ID.
    """
    if not os.path.isdir(output_dir):
        return
    removed = 0
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json"):
            continue
        lid = fname.rsplit(".json", 1)[0].rsplit("_", 1)[-1]
        if not LATTES_ID_RE.fullmatch(lid) or lid not in valid_ids:
            os.remove(os.path.join(output_dir, fname))
            removed += 1
    if removed:
        logger.info(f"Removed {removed} stale JSON files from {output_dir}")


@flow(name="Download Lattes Curricula", **telegram_flow_state_handlers())
def download_lattes_flow():
    base_dir = os.path.abspath("data")
    output_dir = os.path.join(base_dir, "lattes_json")
    cache_dir = os.path.abspath("cache")

    logger.info("Using DB researchers for list generation.")
    researchers = get_researchers_from_db()
    list_path = generate_list(researchers)

    lattes_ids = collect_lattes_ids_from_list(list_path)
    if not lattes_ids:
        logger.warning(
            "No valid 16-digit Lattes IDs found in DB or historical export. "
            "Skipping Lattes download — re-run after lattes_projects has "
            "populated cnpq_url on researcher records."
        )
        return

    _clean_stale_json_files(output_dir, lattes_ids)

    logger.info(f"Preparing to download {len(lattes_ids)} Lattes curricula.")

    if should_skip_download_if_cached(output_dir, lattes_ids):
        logger.info(
            "Skipping Lattes download — all curricula already present in output dir."
        )
        return

    validate_script_lattes_runtime()
    logger.info("Playwright Chromium runtime validated for scriptLattes.")

    effective_list_path = list_path
    if is_lattes_prefetch_enabled():
        prefetch_lattes_cache(
            lattes_ids,
            cache_dir,
            max_workers=get_lattes_prefetch_workers(),
        )
        cache_path = Path(cache_dir)
        failed_ids = {lid for lid in lattes_ids if not (cache_path / lid).exists()}
        if failed_ids:
            tmp_list = os.path.abspath("cache/lattes_effective.list")
            with open(tmp_list, "w") as f:
                for line in Path(list_path).read_text().splitlines():
                    match = LATTES_ID_RE.search(line)
                    if match and match.group(0) in failed_ids:
                        continue
                    f.write(line + "\n")
            effective_list_path = tmp_list
            logger.info(
                f"Excluded {len(failed_ids)} failed IDs from scriptLattes run: {failed_ids}"
            )
    else:
        logger.info(f"Lattes cache prefetch disabled by {LATTES_PREFETCH_ENABLED_ENV}.")

    config_path = generate_config(output_dir, effective_list_path, cache_dir)
    run_script_lattes_real(config_path)


if __name__ == "__main__":
    download_lattes_flow()
