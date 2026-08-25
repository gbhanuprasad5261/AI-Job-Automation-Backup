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
    print("=" * 70)
    print("ELEMENTS CONTAINING JOB TITLES")
    print("=" * 70)

    # Look for common LinkedIn job-result containers
    selectors = [
        "a",
        "div",
        "span",
    ]

    for selector in selectors:

        print()
        print(f"\n--- {selector.upper()} ---")

        elements = page.locator(selector)

        count = elements.count()

        found = 0

        for i in range(count):

            if found >= 30:
                break

            try:

                element = elements.nth(i)

                text = (
                    element.inner_text()
                    .strip()
                )

                if not text:
                    continue

                # Look for job-related text
                keywords = [
                    "Java",
                    "Software Engineer",
                    "Backend",
                    "Developer",
                    "SDE",
                ]

                if any(
                    keyword.lower() in text.lower()
                    for keyword in keywords
                ):

                    # Keep only reasonably sized elements
                    if len(text) <= 500:

                        print()
                        print(
                            f"[{i}] {text[:500]}"
                        )

                        # Print href when available
                        href = element.get_attribute(
                            "href"
                        )

                        if href:

                            print(
                                f"    HREF: {href}"
                            )

                        found += 1

            except Exception:
                pass

    print()
    print("=" * 70)

    input("Press ENTER to finish...")