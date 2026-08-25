from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")

    context = browser.contexts[0]
    page = context.new_page()

    page.goto("https://www.linkedin.com/feed/")

    print("✅ Successfully connected to Chrome!")

    input("Press ENTER to close...")

    browser.close()