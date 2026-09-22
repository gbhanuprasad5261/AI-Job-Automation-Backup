from playwright.sync_api import sync_playwright

JOB_ID = "4466514046"
CDP_URL = "http://127.0.0.1:9222"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_URL)

    page = None
    for context in browser.contexts:
        for pg in context.pages:
            if f"/jobs/view/{JOB_ID}" in pg.url:
                page = pg
                break

    if not page:
        print("Job page not found.")
        raise SystemExit

    page.wait_for_timeout(2000)

    print("=" * 70)
    print("CURRENT JOB TEXT / APPLY CONTROL DIAGNOSTIC")
    print("=" * 70)
    print("URL:", page.url)

    # Search all visible elements containing Apply
    elements = page.locator(
        "text=/apply/i"
    )

    count = elements.count()
    print("VISIBLE ELEMENTS CONTAINING 'APPLY':", count)
    print()

    for i in range(count):
        try:
            el = elements.nth(i)

            if not el.is_visible():
                continue

            text = (el.inner_text() or "").strip().replace("\n", " ")
            tag = el.evaluate("(e) => e.tagName")
            href = el.get_attribute("href")
            aria = el.get_attribute("aria-label")
            role = el.get_attribute("role")
            cls = el.get_attribute("class")

            print(f"--- ELEMENT {i} ---")
            print("TAG:", tag)
            print("TEXT:", text[:500])
            print("HREF:", href)
            print("ARIA:", aria)
            print("ROLE:", role)
            print("CLASS:", cls)
            print()

        except Exception as e:
            print("ERROR:", e)

    print("=" * 70)
    print("CURRENT JOB CONTAINER TEXT")
    print("=" * 70)

    # Find elements whose href points directly to the current job
    current_links = page.locator(
        f'a[href*="/jobs/view/{JOB_ID}"]'
    )

    print("CURRENT JOB LINKS:", current_links.count())

    for i in range(min(current_links.count(), 20)):
        try:
            el = current_links.nth(i)

            print(f"\n--- CURRENT LINK {i} ---")
            print("TEXT:", (el.inner_text() or "").strip()[:500])
            print("HREF:", el.get_attribute("href"))
            print("PARENT TEXT:",
                  (el.locator("xpath=..").inner_text() or "").strip()[:1000])
        except Exception as e:
            print("ERROR:", e)

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)