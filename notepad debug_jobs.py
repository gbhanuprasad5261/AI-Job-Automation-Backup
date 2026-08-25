from playwright.sync_api import sync_playwright


with sync_playwright() as p:

    browser = p.chromium.connect_over_cdp(
        "http://127.0.0.1:9222"
    )

    context = browser.contexts[0]

    page = context.pages[0]

    print("TITLE:", page.title())
    print("URL:", page.url)

    print()
    print("LI COUNT:", page.locator("li").count())

    # ---------------------------------------
    # Find all links containing /jobs/view/
    # ---------------------------------------

    links = page.locator("a")

    job_links = []

    for i in range(links.count()):

        try:

            href = links.nth(i).get_attribute("href")

            if href and "/jobs/view/" in href:

                if href not in job_links:

                    job_links.append(href)

        except Exception:
            pass

    print()
    print("JOB LINKS FOUND:", len(job_links))

    for link in job_links:

        print(link)

    print()
    print("=" * 70)
    print("PAGE TEXT")
    print("=" * 70)

    print(
        page.locator("body").inner_text()[:8000]
    )

    print()
    print("=" * 70)

    input("Press ENTER to finish...")

    p.stop()