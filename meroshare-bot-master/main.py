import argparse
import sys
import time
from pathlib import Path

import neotermcolor
from playwright.sync_api import sync_playwright

from bot.account_manager import AccountManager
from bot.func import (
    SkippableIpoStateError,
    apply_share,
    find_branch_from_bank_request,
    gotoAsba,
    ipo_selector,
    login,
)

# timing constants for throttling behaviour; toggle FAST_MODE to reduce sleeps
FAST_MODE = False
DELAY = 0.3 if FAST_MODE else 0.6
LONG_DELAY = 1.5 if FAST_MODE else 3.0


def safe_logout(page) -> None:
    """Safely logs out of the current Meroshare session."""
    try:
        page.locator(".header-menu__link").first.click(timeout=1500)
        time.sleep(DELAY)
    except Exception:
        pass


def load_accounts(file_path):
    """Load accounts using centralized AccountManager with fallback support.

    Accepts a Path. If the path doesn't exist, attempt to read `bot/demats.txt`
    from package resources so the file is available after `pip install`.
    """
    # If file_path does not exist, try to load packaged demats.txt from bot package
    if not getattr(file_path, "exists", lambda: True)() or (hasattr(file_path, "exists") and not file_path.exists()):
        try:
            import importlib.resources as _res
            data = _res.read_text("bot", "demats.txt")
            file_path.write_text(data, encoding="utf-8")
        except Exception:
            raise FileNotFoundError(f"demats file not found at {file_path} and no packaged fallback available")

    mgr = AccountManager(file_path=file_path)
    raw_accounts = mgr.load_accounts()
    accounts = []
    for a in raw_accounts:
        accounts.append([
            a.get("name", ""),
            a.get("capital_id", ""),
            a.get("username", ""),
            a.get("password", ""),
            a.get("bank", ""),
            str(a.get("kitta", "10")),
            a.get("crn", ""),
            a.get("txn_pin", ""),
            a.get("branch", ""),
            a.get("company", ""),
        ])
    return accounts


def parse_args():
    parser = argparse.ArgumentParser(description="Meroshare IPO auto-apply bot")
    parser.add_argument(
        "--company",
        type=str,
        default="",
        help="Apply only for IPO company name matching this text (case-insensitive)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="run with reduced wait times (may be less reliable on slow connections)",
    )
    parser.add_argument(
        "--engine",
        type=str,
        default="",
        choices=["api", "playwright", ""],
        help="Execution engine: 'api' (ultra-fast direct REST) or 'playwright' (browser)",
    )
    return parser.parse_args()



def main():
    # determine target company (CLI > config.ini > empty)
    args = parse_args()
    target_company = args.company.strip()
    global FAST_MODE, DELAY, LONG_DELAY
    if args.fast:
        FAST_MODE = True
        DELAY = 0.3
        LONG_DELAY = 1.5
    else:
        FAST_MODE = False
        DELAY = 0.6
        LONG_DELAY = 3.0
    engine = args.engine.strip().lower()
    config = None
    try:
        import configparser
        import importlib.resources as _res
        if getattr(__import__('sys'), 'frozen', False):
            exe_dir = Path(__import__('sys').executable).parent
            cfg_candidates = [exe_dir / 'config.ini', exe_dir / '_internal' / 'config.ini']
        else:
            cfg_candidates = [Path.cwd() / 'config.ini', Path(__file__).resolve().parent / 'config.ini']

        config = configparser.ConfigParser()
        found = False
        for cfg in cfg_candidates:
            if cfg.exists():
                config.read(cfg)
                if not target_company:
                    target_company = config.get('general', 'company', fallback='').strip()
                if not engine:
                    engine = config.get('general', 'engine', fallback='api').strip().lower()
                found = True
                break

        if not found:
            try:
                cfg_text = _res.read_text('bot', 'config.ini')
                config.read_string(cfg_text)
                if not target_company:
                    target_company = config.get('general', 'company', fallback='').strip()
                if not engine:
                    engine = config.get('general', 'engine', fallback='api').strip().lower()
            except Exception:
                pass
    except Exception:
        pass

    if not engine:
        engine = "api"

    if engine == "api":
        from bot.account_manager import AccountManager
        from bot.executor import IPOExecutor
        from bot.history_manager import HistoryManager
        from bot.notifications import send_run_summary

        acc_mgr = AccountManager()
        accounts = acc_mgr.load_accounts()
        if not accounts:
            neotermcolor.cprint("No valid accounts found in demats.txt", "red")
            sys.exit(1)

        print("""
    -----------------------------------------------------------------------------------------
    ███╗   ███╗███████╗██████╗  ██████╗ ███████╗██╗  ██╗ █████╗ ██████╗ ███████╗    ██████╗  ██████╗ ████████╗
    ████╗ ████║██╔════╝██╔══██╗██╔═══██╗██╔════╝██║  ██║██╔══██╗██╔══██╗██╔════╝    ██╔══██╗██╔═══██╗╚══██╔══╝
    ██╔████╔██║█████╗  ██████╔╝██║   ██║███████╗███████║███████║██████╔╝█████╗      ██████╔╝██║   ██║   ██║   
    ██║╚██╔╝██║██╔══╝  ██╔══██╗██║   ██║╚════██║██╔══██║██╔══██║██╔══██╗██╔══╝      ██╔══██╗██║   ██║   ██║   
    ██║ ╚═╝ ██║███████╗██║  ██║╚██████╔╝███████║██║  ██║██║  ██║██║  ██║███████╗    ██████╔╝╚██████╔╝   ██║   
    ╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝    ╚═════╝  ╚═════╝    ╚═╝   
                                                                                                             
           -----------------------------------------------------------------------------------------
                               [High-Speed Direct REST API Mode]
           -----------------------------------------------------------------------------------------
        """)
        neotermcolor.cprint(f"Loaded {len(accounts)} accounts. Target: '{target_company or 'First Open Issue'}'", "cyan")

        executor = IPOExecutor(mode="api", delay=DELAY)
        def progress(current, total, name, status, msg):
            color = "green" if status == "SUCCESS" else ("yellow" if status in ("SKIPPED", "STARTING") else "red")
            neotermcolor.cprint(f"[{current}/{total}] {name}: {msg}", color)

        results = executor.run(accounts=accounts, company_name=target_company, progress_callback=progress)

        print("\nRun Summary")
        print("-------------------------------------------")
        print(f"Total Accounts : {results['total']}")
        print(f"Applied        : {len(results['applied'])}")
        print(f"Skipped        : {len(results['skipped'])}")
        print(f"Errors         : {len(results['failed'])}")
        print("-------------------------------------------")

        hm = HistoryManager()
        hm.log_run(
            company_name=target_company or "Open Issue",
            engine="api",
            total=results["total"],
            applied=len(results["applied"]),
            skipped=len(results["skipped"]),
            failed=len(results["failed"]),
            details=results["details"],
        )

        if config:
            try:
                tg_enabled = config.getboolean('telegram', 'enabled', fallback=False)
                tg_token = config.get('telegram', 'bot_token', fallback='').strip()
                tg_chat = config.get('telegram', 'chat_id', fallback='').strip()
                if tg_enabled and tg_token and tg_chat:
                    send_run_summary(tg_token, tg_chat, target_company, results["total"], results["applied"], results["skipped"], results["failed"])
                    neotermcolor.cprint("Dispatched Telegram notification.", "cyan")
            except Exception:
                pass

        if len(results["failed"]) > 0:
            sys.exit(1)
        return

    summary = {
        "total": 0,
        "applied": 0,
        "skipped": 0,
        "login_failed": 0,
        "no_issue": 0,
        "errors": 0,
    }

    with sync_playwright() as p:
        # Description Banner for the tool
        print("""
    -----------------------------------------------------------------------------------------
    ███╗   ███╗███████╗██████╗  ██████╗ ███████╗██╗  ██╗ █████╗ ██████╗ ███████╗    ██████╗  ██████╗ ████████╗
    ████╗ ████║██╔════╝██╔══██╗██╔═══██╗██╔════╝██║  ██║██╔══██╗██╔══██╗██╔════╝    ██╔══██╗██╔═══██╗╚══██╔══╝
    ██╔████╔██║█████╗  ██████╔╝██║   ██║███████╗███████║███████║██████╔╝█████╗      ██████╔╝██║   ██║   ██║   
    ██║╚██╔╝██║██╔══╝  ██╔══██╗██║   ██║╚════██║██╔══██║██╔══██║██╔══██╗██╔══╝      ██╔══██╗██║   ██║   ██║   
    ██║ ╚═╝ ██║███████╗██║  ██║╚██████╔╝███████║██║  ██║██║  ██║██║  ██║███████╗    ██████╔╝╚██████╔╝   ██║   
    ╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝    ╚═════╝  ╚═════╝    ╚═╝   
                                                                                                            
           -----------------------------------------------------------------------------------------
                                        Author: Er. Sudeep Das
           -----------------------------------------------------------------------------------------
        """)
        try:
            browser = p.chromium.launch(headless=True)
        # user-adjustable pacing helpers
        # DELAY is the short sleep between actions; LONG_DELAY is used when
        # the portal occasionally needs a little more time (formerly 5s)
        except Exception as launch_error:
            message = str(launch_error)
            if "Executable doesn't exist" in message or "playwright install" in message:
                neotermcolor.cprint("Playwright browser binaries are missing.", "red")
                neotermcolor.cprint("Run this once, then retry:", "yellow")
                neotermcolor.cprint("  python -m playwright install chromium", "yellow")
                if getattr(sys, 'frozen', False):
                    neotermcolor.cprint("For packaged EXE, run install_playwright.bat in the same folder.", "yellow")
                    try:
                        input("\nPress Enter to close...")
                    except Exception:
                        pass
                raise SystemExit(1)
            raise
        page = browser.new_page(user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36')
        page.goto("https://meroshare.cdsc.com.np")
        # brief pause for initial page load (was 5s)
        time.sleep(LONG_DELAY)

        # Determine demats.txt location
        if getattr(__import__('sys'), 'frozen', False):
            exe_dir = Path(__import__('sys').executable).parent
            demat_path = exe_dir / "demats.txt"
            if not demat_path.exists():
                # Try alternate location used by PyInstaller one-folder (`_internal/demats.txt`).
                alt = exe_dir / "_internal" / "demats.txt"
                if alt.exists():
                    demat_path = alt
                    neotermcolor.cprint(f"Using bundled demats.txt from '{alt.name}'", "green")
                else:
                    # Attempt to write packaged default `bot/demats.txt` to the EXE folder
                    try:
                        import importlib.resources as _res
                        default_data = _res.read_text('bot', 'demats.txt')
                        try:
                            demat_path.write_text(default_data, encoding='utf-8')
                            neotermcolor.cprint(f"Wrote default demats.txt to {demat_path}", "green")
                        except Exception:
                            neotermcolor.cprint(f"demats.txt not found at {demat_path}; using packaged default without writing to disk.", "yellow")
                    except Exception:
                        neotermcolor.cprint(f"demats.txt not found at {demat_path} and no packaged fallback available", "red")
                        browser.close()
                        raise SystemExit(1)
        else:
            cwd_candidate = Path.cwd() / "demats.txt"
            if cwd_candidate.exists():
                demat_path = cwd_candidate
            else:
                demat_path = Path(__file__).resolve().parent / "demats.txt"
        accounts = load_accounts(demat_path)

        if not accounts:
            neotermcolor.cprint("No valid accounts found in demats.txt", "red")
            browser.close()
            raise SystemExit(1)

        for account in accounts:
        # per-run delay constants (can be tuned)

            summary["total"] += 1
            name, dp_id, username, password, bank, kitta, crn, txn_pin, branch, account_company = account
            dp_id_num = dp_id[3:] if dp_id.startswith('130') else dp_id
            print('Working for ' + name + ' :')

            # Company precedence: CLI --company (args.company) > per-account company (demats.txt) > config.ini company
            if args.company.strip():
                effective_company = args.company.strip()
            elif account_company:
                effective_company = account_company
                neotermcolor.cprint(f"Using company from demats.txt: '{effective_company}'", "green")
            else:
                effective_company = target_company

            # allow apply if CLI (--company), per-account Company, or global config.ini company is present
            apply_allowed = bool(args.company.strip() or account_company or target_company)
            if not apply_allowed:
                summary["skipped"] += 1
                neotermcolor.cprint(
                    f"Skipping apply for {name}: add Company in demats.txt for this user or use --company/config.ini to enable apply.",
                    "yellow",
                )
                safe_logout(page)
                neotermcolor.cprint("-------------------------------------------", "yellow")
                continue

            # ensure login form has loaded before attempting login
            try:
                # reduce timeout from 45s to 15s; most pages load quickly
                page.wait_for_selector('#selectBranch', timeout=15000)
            except Exception:
                neotermcolor.cprint(f"Login page did not load for {name}; skipping.", "red")
                summary["login_failed"] += 1
                neotermcolor.cprint("-------------------------------------------","red")
                continue
            login(page,dp_id_num,username,password)
            time.sleep(DELAY)
            try:
                issue_count = gotoAsba(page)
            except Exception:
                summary["login_failed"] += 1
                neotermcolor.cprint(f"Login Error, recheck credentials of {name}","red")
                neotermcolor.cprint("-------------------------------------------","red")
                continue

            try:
                branch_hint = branch or find_branch_from_bank_request(page, bank)
            except Exception as branch_error:
                branch_hint = branch or ""
                neotermcolor.cprint(
                    f"Branch lookup failed for {name}; continuing with available branch value. ({str(branch_error)[:120]})",
                    "yellow",
                )
            if branch_hint:
                neotermcolor.cprint(f"Using branch from My Bank Request: {branch_hint}", "green")

            if issue_count <= 0:
                summary["no_issue"] += 1
                neotermcolor.cprint(f"No open IPO/FPO issue for {name}", "yellow")
                safe_logout(page)
                neotermcolor.cprint("-------------------------------------------", "yellow")
                continue

            try:
                try:
                    ipo_selector(page, issue_count, 1, effective_company)
                except RuntimeError as selector_error:
                    selector_text = str(selector_error)
                    if issue_count == 1 and "Requested company not found" in selector_text:
                        neotermcolor.cprint(
                            f"Company match failed for {name}; only one issue is open, selecting it automatically.",
                            "yellow",
                        )
                        ipo_selector(page, issue_count, 1, "")
                    else:
                        raise
                apply_share(page,bank,kitta,crn,txn_pin,branch_hint)
                time.sleep(LONG_DELAY)
                summary["applied"] += 1
                neotermcolor.cprint("IPO Applied Successfully for " + name,"green")
            except SkippableIpoStateError:
                summary["skipped"] += 1
                neotermcolor.cprint(f"IPO skipped for {name}: IPO Already Applied for the selected company", "yellow")
            except Exception as e:
                summary["errors"] += 1
                neotermcolor.cprint(f"IPO Application Error for {name}: {e!s}","red")
            # Logout
            safe_logout(page)
            neotermcolor.cprint("-------------------------------------------","green")

        browser.close()

        print("\nRun Summary")
        print("-------------------------------------------")
        print(f"Total Accounts : {summary['total']}")
        print(f"Applied        : {summary['applied']}")
        print(f"Skipped        : {summary['skipped']}")
        print(f"Login Failed   : {summary['login_failed']}")
        print(f"No Open Issue  : {summary['no_issue']}")
        print(f"Errors         : {summary['errors']}")
        print("-------------------------------------------")

        if summary["errors"] > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
