"""Debug script to inspect raw Capitol Trades table structure."""
import time
from playwright.sync_api import sync_playwright

URL = "https://www.capitoltrades.com/trades?politician=P000197&pageSize=20&page=1&sortBy=txDate&order=desc"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx  = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_selector("table tbody tr", timeout=20_000)
    time.sleep(2)

    rows = page.evaluate("""
        () => {
            const rows = document.querySelectorAll('table tbody tr');
            const result = [];
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                const cellTexts = [];
                cells.forEach(c => cellTexts.push(c.innerText.trim()));
                result.push(cellTexts);
            });
            return result;
        }
    """)
    browser.close()

print(f"Total rows: {len(rows)}")
print()
for i, row in enumerate(rows[:5]):
    print(f"--- Row {i} ({len(row)} cells) ---")
    for j, cell in enumerate(row):
        print(f"  [{j}]: {repr(cell[:100])}")
    print()
