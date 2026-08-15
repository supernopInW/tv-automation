import time
import sys
import os
import tempfile
from playwright.sync_api import sync_playwright

def main():
    username = os.environ.get('TV_USERNAME', '') or input('Enter username: ')
    password = os.environ.get('TV_PASSWORD', '') or input('Enter password: ')
    
    output_path = os.path.join(tempfile.gettempdir(), 'tv-automation-buttons-info.txt')
    
    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print("Logging in to T&V portal...")
        page.goto("https://tandv.doae.go.th/index/login_tv_system.php")
        page.wait_for_load_state("networkidle")
        page.fill('input[name="USER_NAME"]', username)
        page.fill('input[name="USER_PASSWORD"]', password)
        page.click('#login_submit')
        time.sleep(5)
        
        print("Navigating to Workflow 26 plan form...")
        page.goto("https://tandv.doae.go.th/workflow/workflow_start.php?W=26")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        lines = []
        lines.append("=== BUTTONS AND LINKS ON THE PAGE ===")
        buttons = page.query_selector_all("button, input[type='button'], input[type='submit'], a.btn, a[id*='btn'], a[class*='btn']")
        for idx, btn in enumerate(buttons):
            btn_id = btn.get_attribute("id") or ""
            btn_class = btn.get_attribute("class") or ""
            btn_text = btn.inner_text() or btn.get_attribute("value") or ""
            lines.append(f"Index {idx}: Text='{btn_text.strip()}' | ID='{btn_id}' | Class='{btn_class}'")
            
        lines.append("\n=== ALL WORKFLOW BUTTONS ===")
        wf_buttons = page.query_selector_all("[id*='btn'], [id*='save'], [id*='draft'], [id*='submit']")
        for idx, btn in enumerate(wf_buttons):
            tag = btn.evaluate("el => el.tagName.toLowerCase()")
            btn_id = btn.get_attribute("id") or ""
            btn_text = btn.inner_text() or btn.get_attribute("value") or ""
            lines.append(f"WF Index {idx}: <{tag}> Text='{btn_text.strip()}' | ID='{btn_id}'")
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        print(f"Saved inspection output to {output_path}")
        browser.close()

if __name__ == "__main__":
    main()
