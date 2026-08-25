from playwright.sync_api import sync_playwright

print("Playwright is working!")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://www.linkedin.com")
    print(page.title())
    browser.close()