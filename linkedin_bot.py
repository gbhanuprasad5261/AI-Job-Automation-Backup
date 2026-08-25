from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")

    context = browser.contexts[0]
    page = context.pages[0]

    page.goto("https://www.linkedin.com/jobs/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    print("Title:", page.title())
    print("URL:", page.url)

    input("\nPress ENTER to close...")