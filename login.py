from playwright.sync_api import sync_playwright


def login():
    with sync_playwright() as p:

        context = p.chromium.launch_persistent_context(
            user_data_dir="playwright-profile",
            headless=False,
            viewport=None,
            args=["--start-maximized"]
        )

        page = context.new_page()

        print("Opening LinkedIn...")

        page.goto("https://www.linkedin.com/login")

        print("\n======================================")
        print("1. Login to LinkedIn.")
        print("2. Complete CAPTCHA if it appears.")
        print("3. Wait until LinkedIn Feed opens.")
        print("4. Come back to terminal.")
        print("======================================\n")

        input("Press ENTER after LinkedIn Feed opens...")

        print("\n✅ Login session saved successfully!")

        context.close()


if __name__ == "__main__":
    login()