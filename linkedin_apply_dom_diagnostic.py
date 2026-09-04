from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]

    page = next(
        (pg for pg in context.pages if "linkedin.com/jobs/view/" in pg.url.lower()),
        None
    )

    if page is None:
        print("NO LINKEDIN JOB TAB FOUND")
        raise SystemExit(1)

    print("=" * 70)
    print("LINKEDIN APPLY DOM DIAGNOSTIC")
    print("=" * 70)
    print("URL:", page.url)
    print("TITLE:", page.title())

    locator = page.locator("[aria-label='LinkedIn Apply to this job' i]")
    print("EXACT MATCHES:", locator.count())

    for i in range(locator.count()):
        el = locator.nth(i)

        print()
        print("MATCH", i + 1)
        print("TAG:", el.evaluate("(e) => e.tagName"))
        print("ARIA:", el.get_attribute("aria-label"))
        print("TITLE:", el.get_attribute("title"))
        print("ROLE:", el.get_attribute("role"))
        print("TEXT:", (el.inner_text() or "").strip())
        print("VISIBLE:", el.is_visible())
        print("ENABLED:", el.is_enabled())
        print("HTML:")
        print(el.evaluate("(e) => e.outerHTML")[:3000])

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE — NOTHING CLICKED")
    print("=" * 70)
