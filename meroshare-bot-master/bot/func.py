import difflib
import re
import time

import neotermcolor

from bot.models import SkippableIpoStateError

# High performance mode: reactive waits with minimal debounce delays
FAST_MODE = True
DELAY = 0.15
PAGE_TIMEOUT = 12000


BANK_LABEL_ALIASES = {
    "NIC ASIA BANK LTD": "NIC ASIA BANK LTD.",
    "NABIL BANK LTD": "Nabil Bank Limited.",
    "NABIL BANK LIMITED": "Nabil Bank Limited.",
    "CIVIL BANK LTD": "CIVIL BANK LTD.",
    "NEPAL INVESTMENT BANK LTD": "Nepal Investment Bank Ltd.",
    "GARIMA BIKAS BANK LTD": "GARIMA BIKAS BANK LTD.",
    "MAHALAXMI BIKAS BANK LTD": "Mahalaxmi Bikas Bank Ltd.",
    "NMB BANK LTD": "NMB BANK LTD.",
    "NEPAL SBI BANK LTD": "NEPAL SBI BANK LTD.",
}


def normalize_bank_label(bank):
    key = " ".join(bank.strip().upper().rstrip(".").split())
    return BANK_LABEL_ALIASES.get(key, bank.strip())


def _norm_text(value):
    return " ".join(value.strip().upper().rstrip(".").split())


def _name_token_set(s: str):
    """Return normalized token set for company/issue name matching (stopwords removed)."""
    stopwords = {"company", "co", "ltd", "limited", "the", "pvt", "private", "inc", "plc"}
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", (s or "").lower()) if t not in stopwords]
    return set(tokens)


def select_bank_option(page, bank):
    page.wait_for_selector("#selectBank", timeout=PAGE_TIMEOUT)
    deadline = time.time() + 10
    while time.time() < deadline:
        options = page.locator("#selectBank option").evaluate_all(
            "els => els.map(el => ({label: (el.textContent || '').trim(), value: el.value || ''}))"
        )
        if options and len(options) > 1:
            break
        time.sleep(0.1)

    target = _norm_text(normalize_bank_label(bank))
    options = page.locator("#selectBank option").evaluate_all(
        "els => els.map(el => ({label: (el.textContent || '').trim(), value: el.value || ''}))"
    )

    if not options:
        raise RuntimeError("Bank dropdown has no selectable options")

    selected_value = None
    for option in options:
        label = _norm_text(option["label"])
        if label == target:
            selected_value = option["value"]
            break

    if selected_value is None:
        for option in options:
            label = _norm_text(option["label"])
            if target in label or label in target:
                selected_value = option["value"]
                break

    if selected_value is None:
        fallback_options = []
        for option in options:
            label = _norm_text(option["label"])
            value = option["value"].strip()
            if value and "SELECT" not in label:
                fallback_options.append(option)

        if len(fallback_options) >= 1:
            selected_value = fallback_options[0]["value"]
            neotermcolor.cprint(
                f"Bank '{bank}' matched to '{fallback_options[0]['label']}'.",
                "yellow",
            )

    if selected_value is None:
        available = ", ".join([option["label"] for option in options if option["label"]])
        raise RuntimeError(f"Could not match bank in dropdown: {bank}. Available: {available}")

    page.locator("#selectBank").select_option(value=selected_value, timeout=PAGE_TIMEOUT)


def select_account_option(page, account_hint=''):
    account_select = page.locator("select[id*='account' i], select[name*='account' i], select[id*='branch' i], select[name*='branch' i]").first
    if account_select.count() > 0:
        try:
            option_values = account_select.locator("option").evaluate_all(
                "els => els.map(el => ({label: (el.textContent || '').trim(), value: (el.value || '').trim()}))"
            )
            valid_options = []
            for option in option_values:
                label = option["label"].lower()
                if option["value"] and "choose" not in label and "select" not in label:
                    valid_options.append(option)

            if valid_options:
                selected_value = valid_options[0]["value"]
                if account_hint:
                    for option in valid_options:
                        if account_hint.strip().lower() in option["label"].lower():
                            selected_value = option["value"]
                            break
                account_select.select_option(value=selected_value, timeout=PAGE_TIMEOUT)
                return True
        except Exception:
            pass

    account_input = page.locator("#selectBranch").first
    if account_input.count() == 0:
        account_input = page.locator("input[placeholder*='Account'], input[placeholder*='Branch']").first
    if account_input.count() == 0:
        return False

    try:
        if account_input.is_visible():
            account_input.click(timeout=3000)
            time.sleep(0.15)

            option_selector = "mat-option, .mat-option, .ng-option, [role='option']"
            if account_hint:
                account_input.fill(account_hint)
                time.sleep(0.15)

            branch_options = page.query_selector_all(option_selector)
            for option in branch_options:
                if option.is_visible():
                    text = (option.inner_text() or "").strip()
                    if text and len(text) <= 120:
                        option.click()
                        time.sleep(0.1)
                        return True

            account_input.press("ArrowDown")
            account_input.press("Enter")
            time.sleep(0.1)

            value = account_input.input_value().strip()
            if value:
                return True
    except Exception:
        return False

    return False


def extract_price_per_share(page):
    script = r"""
    () => {
      const text = document.body ? document.body.innerText : '';
      const match = text.match(/Price\s*Per\s*Share\s*([0-9]+)/i);
      return match ? Number(match[1]) : null;
    }
    """
    try:
        return page.evaluate(script)
    except Exception:
        return None


def collect_visible_form_messages(page):
    selectors = [
        ".invalid-feedback",
        ".text-danger",
        "mat-error",
        ".error",
        ".form-error",
        ".help-block",
        ".toast-message",
        ".snackbar-message",
        "[role='alert']",
    ]

    messages = []
    for selector in selectors:
        elements = page.query_selector_all(selector)
        for element in elements:
            if element.is_visible():
                text = (element.inner_text() or "").strip()
                if text and text not in messages:
                    messages.append(text)
    return messages


def get_selected_bank_text(page):
    try:
        return page.locator("#selectBank option:checked").first.inner_text().strip()
    except Exception:
        return ""


def collect_form_control_snapshot(page):
    script = """
    () => {
        const controls = Array.from(document.querySelectorAll('input, select, textarea'));
        const normalized = controls.map(el => ({
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            name: el.name || '',
            placeholder: el.placeholder || '',
            type: el.type || '',
            value: (el.value || '').toString(),
            disabled: !!el.disabled,
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
        }));
        return normalized.filter(item => {
            const key = `${item.id} ${item.name} ${item.placeholder}`.toLowerCase();
            return key.includes('bank') || key.includes('branch') || key.includes('crn') || key.includes('kitta') || key.includes('amount');
        });
    }
    """
    try:
        return page.evaluate(script)
    except Exception:
        return []


def login(page, db_id, username, password):
    page.wait_for_load_state("domcontentloaded")

    branch_selectors = ["#selectBranch", "#selectDp", "select[name*='branch' i]", ".select2-selection", "[aria-haspopup='true']"]
    branch_el = None
    for selector in branch_selectors:
        candidate = page.query_selector(selector)
        if candidate:
            branch_el = candidate
            break

    if not branch_el:
        raise RuntimeError("Login page branch selector not found")

    branch_el.click()

    # Fast reactive wait for DP searchbox
    try:
        search_el = page.wait_for_selector(".select2-search__field, input[role='searchbox'], input.select2-search__field", timeout=4000)
    except Exception:
        search_el = None

    if not search_el:
        raise RuntimeError("DP search field not found on login page")

    search_el.fill(db_id)
    page.keyboard.press("Enter")

    username_el = page.locator("#username, input[name='username'], input[formcontrolname='username']").first
    if username_el.count() == 0:
        username_el = page.locator("input[placeholder*='User' i]").first
    if username_el.count() == 0:
        raise RuntimeError("Username field not found")

    password_el = page.locator("#password, input[name='password'], input[type='password']").first
    if password_el.count() == 0:
        password_el = page.locator("input[formcontrolname='password']").first
    if password_el.count() == 0:
        raise RuntimeError("Password field not found")

    username_el.fill(username)
    password_el.fill(password)

    signin_selectors = [".sign-in", "button[type='submit']", "button:has-text('Login')", "button:has-text('Sign In')"]
    signin_el = None
    for selector in signin_selectors:
        candidate = page.query_selector(selector)
        if candidate:
            signin_el = candidate
            break

    if not signin_el:
        raise RuntimeError("Sign-in button not found")

    signin_el.click()
    try:
        page.wait_for_selector(".header-menu__link, #sideBar, .toast-message, .alert", timeout=7000)
    except Exception:
        pass


def IPODict(list_):
    ipoData = [i.inner_text().split('\n') for i in list_]
    IPOs = [[ipoData.index(ipo) + 1, ipo[0], f'{ipo[4]} {ipo[3]}'] for ipo in ipoData if len(ipo) >= 5]
    return IPOs


def gotoAsba(page):
    """Instant reactive routing to the ASBA issue portal."""
    try:
        asba_link = page.locator("a[href*='#/asba'], a[routerlink*='asba'], a:has-text('ASBA')").first
        if asba_link.is_visible():
            asba_link.click(timeout=1500)
        else:
            page.evaluate("() => { window.location.hash = '#/asba'; }")
    except Exception:
        page.goto("https://meroshare.cdsc.com.np/#/asba", wait_until="domcontentloaded", timeout=10000)

    try:
        page.wait_for_selector(".company-name, .blank-slate, table, .tooltipster-fall", timeout=5000)
    except Exception:
        pass
    share = page.query_selector_all(".company-name")
    return len(share)


def find_branch_from_bank_request(page, bank):
    normalized_bank = _norm_text(bank)
    original_url = page.url

    try:
        page.goto("https://meroshare.cdsc.com.np/#/my-bank-request", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_selector("table tbody tr", timeout=4000)

        rows = page.query_selector_all("table tbody tr")
        for row in rows:
            cells = [cell.inner_text().strip() for cell in row.query_selector_all("td")]
            if not cells:
                continue

            normalized_cells = [_norm_text(cell) for cell in cells]
            match_index = -1
            for index, cell in enumerate(normalized_cells):
                if normalized_bank in cell or cell in normalized_bank:
                    match_index = index
                    break

            if match_index == -1:
                continue

            branch_candidate = ""
            if len(cells) > match_index + 1:
                branch_candidate = cells[match_index + 1].strip()

            if not branch_candidate:
                for candidate in cells:
                    text = candidate.strip()
                    if text and _norm_text(text) not in normalized_bank and re.search(r"[A-Za-z]", text):
                        branch_candidate = text
                        break

            if branch_candidate:
                return branch_candidate
    except Exception:
        return ""
    finally:
        try:
            page.goto(original_url, wait_until="domcontentloaded")
        except Exception:
            pass

    return ""


def ipo_selector(page, total, ind=1, company_query=""):
    """
    Select target IPO and navigate to application form instantly.
    Uses localized container locator to avoid traversing entire DOM.
    """
    if total <= 0:
        raise ValueError("No IPO/FPO issue available to select")

    companies = page.query_selector_all(".company-name")
    if not companies:
        raise RuntimeError("No company-name elements found on ASBA page")

    company_el = None
    selected_index = int(ind)

    if company_query and company_query.strip():
        query = company_query.strip().lower()
        for idx, element in enumerate(companies, start=1):
            text = (element.inner_text() or "").strip().lower()
            q_tokens = _name_token_set(company_query)
            t_tokens = _name_token_set(text)

            matched = False
            if q_tokens and (q_tokens <= t_tokens or t_tokens <= q_tokens):
                matched = True
            elif q_tokens and t_tokens:
                overlap = len(q_tokens & t_tokens) / max(len(q_tokens), len(t_tokens))
                if overlap >= 0.55:
                    matched = True
            elif query in text or text in query:
                matched = True
            else:
                ratio = difflib.SequenceMatcher(None, query, text).ratio()
                if ratio >= 0.70:
                    matched = True

            if matched:
                company_el = element
                selected_index = idx
                break

        if company_el is None:
            available = [((element.inner_text() or "").strip()) for element in companies]
            raise RuntimeError(
                f"Requested company not found: '{company_query}'. Available issues: {', '.join(available)}"
            )
    else:
        if selected_index < 1 or selected_index > total:
            raise ValueError(f"Issue index out of range: {selected_index}")
        company_el = companies[selected_index - 1]

    company_name = (company_el.inner_text() or "").split('\n')[0].strip()

    # Find the apply button inside the parent container/row
    apply_btn = None
    try:
        parent_box = company_el.evaluate_handle(
            "el => el.closest('.row, .company-list, .card, [class*=\"company\"], div') || el.parentElement"
        )
        if parent_box:
            cand = parent_box.query_selector("button, a")
            if cand:
                txt = (cand.inner_text() or "").strip().lower()
                if re.search(r"\b(apply|re-?apply)\b", txt):
                    apply_btn = cand
    except Exception:
        apply_btn = None

    if not apply_btn:
        # Fallback to direct locator search
        try:
            apply_candidates = page.locator("button:has-text('Apply'), a:has-text('Apply'), .btn-issue")
            if apply_candidates.count() >= selected_index:
                apply_btn = apply_candidates.nth(selected_index - 1)
        except Exception:
            apply_btn = None

    if apply_btn is None:
        try:
            card_text = (company_el.evaluate("el => (el.closest('.row') || el.closest('div')).innerText") or "").lower()
            skip_words = ("view", "update", "edit", "applied", "modify", "verified")
            if any(word in card_text for word in skip_words) and not re.search(r"\bre-?apply\b", card_text):
                raise SkippableIpoStateError(f"IPO Already Applied for company '{company_name}'")
        except SkippableIpoStateError:
            raise
        except Exception:
            pass
        raise RuntimeError(f"Unable to locate apply button for '{company_name}'")

    # Click apply
    try:
        apply_btn.click(timeout=4000)
    except Exception as e:
        raise RuntimeError(f"Failed to click Apply for '{company_name}': {e}")

    # Reactively wait for form fields to appear
    form_opened = False
    try:
        page.wait_for_selector("#appliedKitta, #crnNumber", timeout=4000)
        form_opened = True
    except Exception:
        pass

    if not form_opened:
        # Check if Angular router link can be triggered via hash
        route = ""
        try:
            route = page.evaluate("""() => {
                const nodes = Array.from(document.querySelectorAll('a, button, [routerLink]'));
                for (const n of nodes) {
                    const r = n.getAttribute('routerlink') || n.getAttribute('href') || '';
                    if (r.includes('/asba/apply/')) return r;
                }
                return '';
            }""")
        except Exception:
            route = ""

        if route:
            clean_hash = route.lstrip("#")
            page.evaluate(f"() => {{ window.location.hash = '{clean_hash}'; }}")
            try:
                page.wait_for_selector("#appliedKitta, #crnNumber", timeout=5000)
                form_opened = True
            except Exception:
                pass

    if not form_opened:
        raise SkippableIpoStateError(
            f"Apply clicked but IPO form did not open for '{company_name}'. Likely already applied or account not eligible."
        )

    neotermcolor.cprint("IPO Application Section Reached", "green")


def apply_share(page, bank, kitta, crn, txn_no, branch_hint=''):
    """Fill and submit ASBA application form reactively."""
    page.wait_for_selector("#appliedKitta", timeout=PAGE_TIMEOUT)

    # 1. Select Bank
    select_bank_option(page, bank)
    time.sleep(0.2)

    # 2. Select Account / Branch
    select_account_option(page, branch_hint)
    time.sleep(0.1)

    # 3. Enter Kitta
    page.locator("#appliedKitta").fill(str(kitta), timeout=PAGE_TIMEOUT)

    # 4. Check Amount field
    amount_input = page.locator("#amount")
    if amount_input.count() > 0:
        try:
            if amount_input.is_editable() and not amount_input.input_value().strip():
                price = extract_price_per_share(page)
                if price:
                    amount_input.fill(str(int(kitta) * int(price)), timeout=PAGE_TIMEOUT)
        except Exception:
            pass

    # 5. Enter CRN
    page.locator("#crnNumber").fill(crn, timeout=PAGE_TIMEOUT)

    # 6. Check Terms / Disclaimer
    disclaimer = page.locator("#disclaimer")
    try:
        if not disclaimer.is_checked():
            disclaimer.check(timeout=1500)
    except Exception:
        try:
            page.locator("label[for='disclaimer']").click(timeout=1500)
        except Exception:
            pass

    # 7. Wait for Proceed button to become active
    proceed_button = None
    try:
        page.wait_for_function(
            "() => { const b = document.querySelector('button.btn-primary, button:has-text(\"Proceed\"), form button[type=\"submit\"]'); return b && !b.disabled; }",
            timeout=2500
        )
    except Exception:
        pass

    try:
        proceed_button = page.locator("button:has-text('Proceed'), button[type='submit']").first
    except Exception:
        proceed_button = None

    if not proceed_button or proceed_button.count() == 0:
        candidates = page.query_selector_all("button, a")
        for node in candidates:
            try:
                if node.is_visible() and re.search(r"\b(proceed|next|submit|continue)\b", (node.inner_text() or "").lower()):
                    proceed_button = node
                    break
            except Exception:
                continue

    if not proceed_button:
        raise RuntimeError("Proceed button not found on IPO form")

    # Click Proceed
    try:
        proceed_button.click(timeout=PAGE_TIMEOUT)
    except Exception as e:
        # Check if form errors explain why
        messages = collect_visible_form_messages(page)
        if messages:
            raise RuntimeError(f"Cannot proceed: {' | '.join(messages)}")
        raise RuntimeError(f"Failed to click Proceed: {e}")

    # 8. Enter Transaction PIN
    try:
        page.wait_for_selector("#transactionPIN", timeout=5000)
    except Exception:
        raise RuntimeError("Transaction PIN field did not appear after Proceed")

    page.locator("#transactionPIN").fill(txn_no, timeout=PAGE_TIMEOUT)

    # 9. Click Final Apply Button
    apply_modal_btn = page.locator("button:has-text('Apply'), .modal-footer button.btn-primary").first
    apply_modal_btn.click(timeout=PAGE_TIMEOUT)

    # 10. Wait for server response / toast feedback
    try:
        page.wait_for_selector(".toast-message, .alert, .swal2-container", timeout=4000)
    except Exception:
        pass

    messages = collect_visible_form_messages(page)
    for msg in messages:
        if re.search(r"\balready\b|duplicate|existing|previous|applied", msg, re.IGNORECASE):
            raise SkippableIpoStateError("IPO Already Applied for the selected company")
        if re.search(r"\berror\b|invalid pin|failed|insufficient|rejected", msg, re.IGNORECASE):
            raise RuntimeError(f"Application rejected: {msg}")

    neotermcolor.cprint("IPO Applied Successfully", "green")

    # Logout to free session
    try:
        page.locator(".header-menu__link").click(timeout=1500)
    except Exception:
        pass
