"""Record completed MKSAP and AMBOSS question counts by date."""
import argparse
import asyncio
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, async_playwright

OUT = Path("question_counts.json")
EASTERN = ZoneInfo("America/New_York")


async def fill_first(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        if await locator.count() and await locator.is_visible():
            await locator.fill(value)
            return True
    return False


async def click_first(page: Page, pattern: re.Pattern[str]) -> bool:
    for role in ("button", "link"):
        locator = page.get_by_role(role, name=pattern).first
        if await locator.count() and await locator.is_visible():
            await locator.click(timeout=5_000)
            return True
    locator = page.get_by_text(pattern).first
    if await locator.count() and await locator.is_visible():
        await locator.click(timeout=5_000)
        return True
    return False


async def mksap_page_context(page: Page, response_status: int | None = None) -> str:
    controls = await page.locator("a, button, [role='button']").all_inner_texts()
    labels = [
        label.strip()
        for label in controls
        if label.strip() and re.search(r"question|bank|menu|nav|expand|study", label, re.I)
    ]
    top_left = await page.locator("button, [role='button']").evaluate_all(
        """elements => elements.map(element => {
            const rect = element.getBoundingClientRect();
            return {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                label: element.getAttribute('aria-label') || element.title || '',
                text: (element.innerText || '').trim(),
                className: String(element.className).slice(0, 80)
            };
        }).filter(item => item.x >= 0 && item.x < 160 && item.y >= 0 && item.y < 120)
          .slice(0, 10)"""
    )
    page_state = await page.evaluate(
        """() => ({
            readyState: document.readyState,
            bodyCharacters: document.body?.innerText?.trim().length || 0,
            controlCount: document.querySelectorAll('a, button, [role="button"]').length,
            iframeCount: document.querySelectorAll('iframe').length
        })"""
    )
    return (
        f"URL: {page.url.split('?')[0]}; response status: {response_status}; "
        f"matching controls: {labels[:20]}; "
        f"top-left controls: {top_left}; page state: {page_state}"
    )


async def login_if_needed(
    page: Page, username: str, password: str, service_name: str
) -> None:
    password_input = page.locator('input[type="password"]').first
    try:
        await password_input.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        return

    user_found = await fill_first(
        page,
        [
            'input[autocomplete="username"]',
            'input[type="email"]',
            'input[name*="username" i]',
            'input[id*="username" i]',
            'input[name*="email" i]',
            'input[id*="email" i]',
            'input[name*="user" i]',
            'input[id*="user" i]',
        ],
        username,
    )
    if not user_found:
        raise RuntimeError("Login form is visible, but its username/email field was not found.")

    await password_input.fill(password)
    submit = page.locator('button[type="submit"], input[type="submit"]').first
    if await submit.count() and await submit.is_visible():
        await submit.click()
    else:
        submit_button = page.get_by_role(
            "button", name=re.compile(r"log\s*in|sign\s*in", re.I)
        ).first
        if not await submit_button.count() or not await submit_button.is_visible():
            raise RuntimeError("Login form is visible, but its submit button was not found.")
        await submit_button.click()
    await page.wait_for_load_state("domcontentloaded")
    try:
        await password_input.wait_for(state="hidden", timeout=15_000)
    except PlaywrightTimeoutError:
        body = await page.locator("body").inner_text()
        if re.search(r"captcha|robot|verification required", body, re.I):
            reason = f"{service_name} requires an interactive verification step."
        elif re.search(r"invalid credentials|incorrect password|login failed|authentication failed", body, re.I):
            reason = f"{service_name} rejected the submitted credentials."
        else:
            reason = f"The {service_name} login form remained visible after submission."
        alert_visible = await page.locator(
            '[role="alert"], [aria-live="assertive"]'
        ).count()
        detail = " A login alert is visible." if alert_visible else " No login alert was detected."
        raise RuntimeError(
            reason + detail + " Check the account login manually; do not share its password."
        )


async def dismiss_amboss_consent(page: Page) -> None:
    dialog = page.get_by_role("dialog").filter(
        has_text=re.compile(r"storage|cookie|privacy|consent", re.I)
    ).first
    if not await dialog.count() or not await dialog.is_visible():
        return

    safe_choices = (
        re.compile(r"only\s+(?:allow\s+)?(?:necessary|essential)|(?:necessary|essential)\s+only", re.I),
        re.compile(r"reject\s+(?:all|optional|non[- ]essential)|decline\s+(?:all|optional)", re.I),
    )
    for choice in safe_choices:
        button = dialog.get_by_role("button", name=choice).first
        if await button.count() and await button.is_visible():
            await button.click()
            await dialog.wait_for(state="hidden", timeout=10_000)
            return

    labels = await dialog.get_by_role("button").all_inner_texts()
    raise RuntimeError(
        "AMBOSS showed a consent dialog without a necessary-only/reject option. "
        f"Visible choices: {labels}"
    )


async def read_mksap_count(page: Page, username: str, password: str) -> int:
    await page.goto("https://mksap.acponline.org", wait_until="domcontentloaded")
    await login_if_needed(page, username, password, "MKSAP")

    response = await page.goto(
        "https://mksap.acponline.org/app/question-bank",
        wait_until="domcontentloaded",
    )
    try:
        await page.wait_for_function(
            """() => document.body && (
                /[\d,]+\s+completed\s+questions?/i.test(document.body.innerText) ||
                /[\d,]+\s+questions?\s+(completed|answered)/i.test(document.body.innerText)
            )""",
            timeout=20_000,
        )
    except PlaywrightTimeoutError:
        pass
    text = await page.locator("body").inner_text()
    count_patterns = (
        r"([\d,]+)\s+completed\s+questions?",
        r"([\d,]+)\s+questions?\s+(?:completed|answered)",
        r"(?:completed|answered)\s+questions?\s*[:\-]?\s*([\d,]+)\b",
        r"questions?\s+(?:completed|answered)\s*[:\-]?\s*([\d,]+)\b",
    )
    for pattern in count_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return int(match.group(1).replace(",", ""))

    count_lines = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"completed|answered|progress|total", line, re.I)
    ][:10]
    if not count_lines:
        count_lines = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"question", line, re.I)
        ][:5]
    if not count_lines:
        count_lines = ["No count-related text was visible."]
    if count_lines:
        raise RuntimeError(
            f"Could not find the MKSAP completed-question count. Text clues: {count_lines}. "
            + await mksap_page_context(page, response.status if response else None)
        )


async def read_amboss_count(page: Page, email: str, password: str) -> tuple[str, int]:
    await page.goto("https://next.amboss.com/us/login", wait_until="domcontentloaded")
    await dismiss_amboss_consent(page)
    await login_if_needed(page, email, password, "AMBOSS")

    await click_first(page, re.compile(r"bank\s+and\s+courses", re.I))
    await click_first(page, re.compile(r"^learning$", re.I))
    await click_first(page, re.compile(r"^analysis$", re.I))
    await page.wait_for_timeout(2_000)

    text = await page.locator("body").inner_text()
    bank_match = re.search(r"your\s+performance\s+analysis\s+for\s+([^\n]+)", text, re.I)
    if not bank_match:
        raise RuntimeError("Could not identify the AMBOSS bank on the performance analysis page.")
    count_match = re.search(r"questions\s+answered\s+([\d,]+)\s+out\s+of\s+([\d,]+)", text, re.I)
    if not count_match:
        raise RuntimeError("Could not find the AMBOSS questions-answered count.")
    return bank_match.group(1).strip(), int(count_match.group(1).replace(",", ""))


def record_counts(mksap: int, amboss_bank: str, amboss: int) -> None:
    data = json.loads(OUT.read_text()) if OUT.exists() else {"mksap": {}, "amboss": {}}
    date = datetime.now(EASTERN).date().isoformat()
    data.setdefault("mksap", {})[date] = mksap
    data.setdefault("amboss", {}).setdefault(amboss_bank, {})[date] = amboss
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {date}: MKSAP {mksap}; AMBOSS {amboss_bank} {amboss}")


def wait_for_scheduled_window() -> None:
    now = datetime.now(EASTERN)
    if not (now.hour == 20 and now.minute >= 30 or now.hour == 21 and now.minute <= 30):
        raise SystemExit("Scheduled run is outside the 8:30-9:30pm Eastern window; skipping.")

    target = now.replace(hour=20, minute=45, second=0, microsecond=0) + timedelta(
        minutes=random.randint(0, 30)
    )
    delay = max(0, (target - now).total_seconds())
    if delay:
        time.sleep(delay)


async def scrape() -> None:
    mksap_user = os.environ["MKSAP_USERNAME"]
    mksap_password = os.environ["MKSAP_PASSWORD"]
    amboss_email = os.environ["AMBOSS_EMAIL"]
    amboss_password = os.environ["AMBOSS_PASSWORD"]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            mksap_count = await read_mksap_count(page, mksap_user, mksap_password)
            amboss_bank, amboss_count = await read_amboss_count(
                page, amboss_email, amboss_password
            )
            record_counts(mksap_count, amboss_bank, amboss_count)
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    if args.scheduled:
        wait_for_scheduled_window()
    asyncio.run(scrape())


if __name__ == "__main__":
    main()