from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_URL)

    context = browser.contexts[0]

    page = None
    for tab in context.pages:
        if "linkedin.com" in tab.url:
            page = tab
            break

    if page is None:
        print("ERROR: LinkedIn tab not found")
        raise SystemExit

    print("=" * 80)
    print("RADIO DOM DIAGNOSTIC - READ ONLY")
    print("=" * 80)
    print("URL:", page.url)

    dialogs = page.get_by_role("dialog")

    if dialogs.count() == 0:
        print("ERROR: LinkedIn application dialog not found")
        raise SystemExit

    dialog = None

    for i in range(dialogs.count()):
        d = dialogs.nth(i)
        try:
            if d.is_visible():
                dialog = d
                break
        except Exception:
            pass

    if dialog is None:
        print("ERROR: No visible application dialog")
        raise SystemExit

    print("Application dialog found.")

    radios = dialog.locator(
        "input[type='radio'], [role='radio']"
    )

    print()
    print("TOTAL RADIO CONTROLS:", radios.count())
    print()

    for i in range(radios.count()):

        radio = radios.nth(i)

        print("-" * 80)
        print("RADIO", i + 1)

        try:
            print("tag:", radio.evaluate("el => el.tagName"))
        except:
            pass

        for attr in [
            "id",
            "name",
            "type",
            "value",
            "aria-label",
            "aria-labelledby",
            "role",
            "checked",
        ]:
            try:
                print(
                    f"{attr}:",
                    radio.get_attribute(attr)
                )
            except:
                pass

        try:
            print(
                "is_checked:",
                radio.is_checked()
            )
        except:
            print("is_checked: unavailable")

        try:
            print(
                "visible:",
                radio.is_visible()
            )
        except:
            pass

        try:
            print()
            print("RADIO OUTER HTML:")
            print(
                radio.evaluate(
                    "el => el.outerHTML"
                )
            )
        except Exception as e:
            print("outerHTML error:", e)

        print()
        print("PARENT OUTER HTML:")

        try:
            parent_html = radio.evaluate(
                """el => {
                    let p = el.parentElement;
                    return p ? p.outerHTML : "";
                }"""
            )
            print(parent_html[:5000])
        except Exception as e:
            print("parent error:", e)

        print()
        print("ANCESTOR TEXT:")

        try:
            text = radio.evaluate(
                """el => {
                    let node = el;
                    let result = [];
                    for (let i = 0; node && i < 8; i++, node = node.parentElement) {
                        result.push(
                            "LEVEL " + i + ":\\n" +
                            (node.innerText || "").slice(0, 1000)
                        );
                    }
                    return result.join("\\n---\\n");
                }"""
            )
            print(text)
        except Exception as e:
            print("ancestor text error:", e)

    print()
    print("=" * 80)
    print("QUESTION-TEXT ELEMENTS")
    print("=" * 80)

    for phrase in [
        "Bachelor",
        "fresher",
        "current salary",
        "notice period",
    ]:

        print()
        print("SEARCH:", phrase)

        elements = dialog.get_by_text(
            __import__("re").compile(
                phrase,
                __import__("re").IGNORECASE
            )
        )

        print("matches:", elements.count())

        for i in range(min(elements.count(), 10)):
            element = elements.nth(i)

            try:
                if not element.is_visible():
                    continue

                print("-" * 60)
                print(
                    "TEXT:",
                    element.inner_text()[:1000]
                )

                print(
                    "TAG:",
                    element.evaluate("el => el.tagName")
                )

                print(
                    "OUTER HTML:"
                )

                print(
                    element.evaluate(
                        "el => el.outerHTML"
                    )[:5000]
                )

            except Exception as e:
                print("element error:", e)

    print()
    print("=" * 80)
    print("DIAGNOSTIC COMPLETE - NOTHING WAS CLICKED")
    print("=" * 80)