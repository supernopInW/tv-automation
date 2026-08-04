import time
from playwright.sync_api import sync_playwright

def main():
    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("Navigating to DOAE T&V portal...")
        page.goto("https://tandv.doae.go.th/")
        
        print("\n=== INSTRUCTIONS FOR USER ===")
        print("1. Please log into the portal on the browser window that just opened.")
        print("2. Once logged in, navigate to Workflow 26 (https://tandv.doae.go.th/workflow/workflow_start.php?W=26)")
        print("3. The script will automatically detect when you are on that page and inspect the form.")
        print("=============================\n")
        
        # Poll URL until it matches the target workflow
        detected = False
        last_url = ""
        while not detected:
            try:
                current_url = page.url
                if current_url != last_url:
                    print(f"Browser URL changed to: {current_url}")
                    last_url = current_url
                
                # Check case-insensitive
                if "workflow_start.php" in current_url.lower() and "w=26" in current_url.lower():
                    print(f"Detected target page: {current_url}")
                    detected = True
                else:
                    time.sleep(0.5)
            except Exception as e:
                time.sleep(1)
                
        print("Waiting for page load...")
        page.wait_for_load_state("networkidle")
        
        # Grab HTML of form elements
        print("Inspecting form inputs...")
        inputs = page.query_selector_all("input, select, textarea, button")
        
        with open("form_structure.txt", "w", encoding="utf-8") as f:
            f.write(f"URL: {page.url}\n")
            f.write(f"Page Title: {page.title()}\n\n")
            f.write("=== FORM ELEMENTS ===\n")
            
            for idx, el in enumerate(inputs):
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                el_id = el.get_attribute("id") or ""
                el_name = el.get_attribute("name") or ""
                el_type = el.get_attribute("type") or ""
                el_value = el.get_attribute("value") or ""
                el_placeholder = el.get_attribute("placeholder") or ""
                
                # Get surrounding label or visible text
                text = el.inner_text() or ""
                if not text and tag == "button":
                    text = el.text_content() or ""
                
                info = f"Element {idx}: <{tag} id='{el_id}' name='{el_name}' type='{el_type}' placeholder='{el_placeholder}'> Text: {text.strip()}\n"
                print(info, end="")
                f.write(info)
                
            # Also write page source of body
            body_html = page.locator("body").inner_html()
            with open("body.html", "w", encoding="utf-8") as html_f:
                html_f.write(body_html)
                
        print("\nForm structure saved to C:\\Users\\Admin\\Downloads\\tv_automation\\form_structure.txt")
        print("Full page body HTML saved to C:\\Users\\Admin\\Downloads\\tv_automation\\body.html")
        
        print("\nLeaving the browser open. Press Ctrl+C in terminal when done to close.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Closing browser...")

if __name__ == "__main__":
    main()
