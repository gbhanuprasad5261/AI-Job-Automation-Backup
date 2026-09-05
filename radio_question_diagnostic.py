from playwright.sync_api import sync_playwright

URL = "https://www.linkedin.com/jobs/view/4459764453/"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")

    contexts = browser.contexts

    if not contexts:
        print("No Chrome context found.")
        raise SystemExit

    pages = []
    for context in contexts:
        pages.extend(context.pages)

    print("Pages found:", len(pages))

    target = None

    for page in pages:
        try:
            text = page.locator("body").inner_text()
            if "Paste a link to code you have written" in text:
                target = page
                break
        except Exception:
            pass

    if target is None:
        print("Application page not found.")
        print("Open the LinkedIn Easy Apply form first.")
        raise SystemExit

    print("TARGET PAGE:")
    print(target.url)
    print()

    matches = target.get_by_text(
        "Paste a link to code you have written",
        exact=False
    )

    print("QUESTION TEXT MATCHES:", matches.count())

    for i in range(matches.count()):
        element = matches.nth(i)

        try:
            if not element.is_visible():
                continue
        except Exception:
            continue

        print()
        print("=" * 70)
        print("MATCH", i + 1)
        print("=" * 70)

        try:
            print("TAG:", element.evaluate("(e) => e.tagName"))
        except Exception:
            pass

        try:
            print("TEXT:", element.inner_text())
        except Exception:
            pass

        print()
        print("OUTER HTML:")
        try:
            print(element.evaluate("(e) => e.outerHTML"))
        except Exception as e:
            print("Could not read HTML:", e)

        print()
        print("ANCESTORS:")

        node = element

        for level in range(1, 9):
            try:
                node = node.locator("xpath=..").first

                if node.count() == 0:
                    break

                print()
                print(f"--- ANCESTOR LEVEL {level} ---")

                print(
                    node.evaluate(
                        "(e) => e.tagName + ' ' + "
                        "(e.getAttribute('role') || '') + ' ' + "
                        "(e.getAttribute('aria-label') || '')"
                    )
                )

                html = node.evaluate("(e) => e.outerHTML")

                # Keep diagnostic output manageable.
                if len(html) > 5000:
                    html = html[:5000] + "\n...[TRUNCATED]..."

                print(html)

            except Exception as e:
                print("Ancestor inspection error:", e)
                break

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("NOTHING WAS CLICKED OR SUBMITTED.")
    print("=" * 70)