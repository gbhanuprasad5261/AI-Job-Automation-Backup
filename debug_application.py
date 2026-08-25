from playwright.sync_api import sync_playwright

with sync_playwright() as p:

    browser = p.chromium.connect_over_cdp(
        "http://127.0.0.1:9222"
    )

    context = browser.contexts[0]
    page = context.pages[0]

    print("=" * 70)
    print("APPLICATION FORM DEBUG")
    print("=" * 70)

    print("TITLE:", page.title())
    print("URL:", page.url)

    print("\nBUTTONS:")
    buttons = page.locator("button")

    for i in range(buttons.count()):
        try:
            b = buttons.nth(i)

            print(
                f"[{i}] "
                f"TEXT={b.inner_text()!r} "
                f"ARIA={b.get_attribute('aria-label')!r}"
            )

        except:
            pass

    print("\nINPUTS:")

    inputs = page.locator("input")

    for i in range(inputs.count()):
        try:
            element = inputs.nth(i)

            print(
                f"[{i}] "
                f"TYPE={element.get_attribute('type')!r} "
                f"NAME={element.get_attribute('name')!r} "
                f"ID={element.get_attribute('id')!r} "
                f"PLACEHOLDER={element.get_attribute('placeholder')!r}"
            )

        except:
            pass

    print("\nTEXTAREAS:")

    textareas = page.locator("textarea")

    for i in range(textareas.count()):
        try:
            element = textareas.nth(i)

            print(
                f"[{i}] "
                f"NAME={element.get_attribute('name')!r} "
                f"PLACEHOLDER={element.get_attribute('placeholder')!r}"
            )

        except:
            pass

    print("\nSELECTS:")

    selects = page.locator("select")

    for i in range(selects.count()):
        try:
            element = selects.nth(i)

            print(
                f"[{i}] "
                f"NAME={element.get_attribute('name')!r} "
                f"ID={element.get_attribute('id')!r}"
            )

        except:
            pass

    print("\nVISIBLE TEXT:")
    print(page.locator("body").inner_text()[:12000])

    input("\nPress ENTER to finish...")