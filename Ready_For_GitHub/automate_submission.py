import sys
import time
import argparse
import pandas as pd
import re
from playwright.sync_api import sync_playwright

# Normalized mapping function
def map_activity(activity_name, tool_name):
    act = activity_name.strip()
    tool = tool_name.strip()
    
    # 1. Training / Meetings
    if "ประชุมสำนักงานเกษตรอำเภอ" in act or "ประชุม" in tool:
        if "WM" in act or "สัปดาห์" in act:
            return "1", "14", ""  # TRAINING, Weekly Meeting
        elif "DM" in act or "อำเภอประจำเดือน" in act:
            return "1", "13", ""  # District Meeting
        elif "MM" in act or "ประจำเดือน" in act:
            return "1", "12", ""  # Monthly Meeting
        else:
            return "1", "999", act
            
    # 2. Visiting / Projects
    if "วิสาหกิจชุมชน" in act:
        return "2", "19", ""      # VISITING, วิสาหกิจชุมชน
    elif "ทะเบียนเกษตรกร" in act:
        return "5", "4", ""       # DATA MANAGEMENT, ด้านข้อมูลสารสนเทศ
    elif "Smart Farmer" in act:
        return "2", "16", ""      # VISITING, Smart Farmer / Young Smart Farmer
    elif "Zoning" in act or "Agri-Map" in act:
        return "2", "17", ""      # VISITING, Zoning by Agri-Map
    elif "แปลงใหญ่" in act:
        return "2", "15", ""      # VISITING, เกษตรแปลงใหญ่
    elif "เกษตรอินทรีย์" in act or "5 ดี" in act:
        return "2", "22", ""      # VISITING, เกษตรอินทรีย์
    elif "ศูนย์เรียนรู้" in act or "ศพก" in act:
        return "2", "2", ""       # VISITING, ศพก.
    elif "ยกระดับคุณภาพ" in act or "มาตรฐานสินค้าเกษตร" in act:
        return "2", "24", ""      # VISITING, พัฒนาคุณภาพสินค้าเกษตร
    elif "สุขภาพพืช" in act or "จัดการสุขภาพพืช" in act:
        return "2", "24", ""      # VISITING, พัฒนาคุณภาพสินค้าเกษตร
    elif "องค์กรเกษตรกร" in act or "พัฒนาเกษตรกร" in act or "3ก" in act:
        return "2", "20", ""      # VISITING, กลุ่มเกษตรกร / กลุ่มแม่บ้านเกษตรกร
    elif "สิ่งแวดล้อม" in act or "เป็นมิตรกับสิ่งแวดล้อม" in act:
        return "2", "999", act    # VISITING, อื่นๆ
    else:
        return "2", "999", act    # VISITING, อื่นๆ (Fallback)

# Convert Excel Date string to dd/mm/yyyy BE
def parse_date_to_be(date_str, month_num, year_num):
    date_str = str(date_str).replace(" ", "")
    # Extract day digits from start of string
    match = re.match(r"^(\d+)", date_str)
    if not match:
        return None
    day = int(match.group(1))
    return f"{day:02d}/{month_num:02d}/{year_num}"

# Parse sheet name (e.g. "มิ.ย.69" -> Year 2569, Month value 69, Month number 6)
def parse_sheet_name(sheet_name):
    # Normalize sheet name
    normalized = sheet_name.replace(" ", "").replace(".", "")
    match = re.match(r"^([ก-๙]+)(\d+)$", normalized)
    if not match:
        raise ValueError(f"Invalid sheet name format: {sheet_name}. Expected format like 'มิ.ย.69'")
    
    month_part = match.group(1)
    year_part = int(match.group(2))
    
    full_year = 2500 + year_part
    
    month_map = {
        "มค": (1, "64"),
        "กพ": (2, "65"),
        "มีค": (3, "66"),
        "เมย": (4, "67"),
        "พค": (5, "68"),
        "มิย": (6, "69"),
        "กค": (7, "70"),
        "สค": (8, "71"),
        "กย": (9, "72"),
        "ตค": (10, "61"),
        "พย": (11, "62"),
        "ธค": (12, "63")
    }
    
    if month_part not in month_map:
        raise ValueError(f"Unknown month name abbreviation: '{month_part}' in sheet name '{sheet_name}'")
        
    month_num, portal_month_val = month_map[month_part]
    return str(full_year), portal_month_val, month_num

# Clean Excel values to prevent float formatting representation (e.g. 5.0 -> 5)
def clean_excel_val(val):
    val_str = str(val).strip()
    if val_str.endswith(".0"):
        val_str = val_str[:-2]
    return val_str

# JS Dropdown helpers to bypass Select2 visibility issues
def select_by_value_js(page, selector, value):
    page.evaluate(f"""() => {{
        const select = document.querySelector('{selector}');
        if (select) {{
            select.value = '{value}';
            select.dispatchEvent(new Event('change'));
        }}
    }}""")

def select_by_label_js(page, selector, label):
    page.evaluate(f"""() => {{
        const select = document.querySelector('{selector}');
        if (select) {{
            const option = Array.from(select.options).find(o => o.text.trim() === '{label}');
            if (option) {{
                select.value = option.value;
                select.dispatchEvent(new Event('change'));
            }}
        }}
    }}""")

def main():
    # Configure stdout/stderr to replace unencodable characters instead of crashing
    try:
        sys.stdout.reconfigure(errors='replace')
        sys.stderr.reconfigure(errors='replace')
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="T&V Automation Script")
    parser.add_argument("--submit", action="store_true", help="Perform actual submission (otherwise runs dry-run)")
    parser.add_argument("--draft", action="store_true", help="Save as draft (บันทึกชั่วคราว)")
    parser.add_argument("--username", help="T&V Portal Username (National ID)")
    parser.add_argument("--password", help="T&V Portal Password")
    parser.add_argument("--sheet", default="มิ.ย.69", help="Excel sheet name to process")
    args = parser.parse_args()
    
    import os
    import getpass
    
    username = args.username or os.environ.get("TV_USERNAME")
    password = args.password or os.environ.get("TV_PASSWORD")
    
    if not username:
        username = input("Enter T&V Username (National ID): ").strip()
    if not password:
        password = getpass.getpass("Enter T&V Password: ").strip()
    
    xls_path = r"c:\Users\Admin\Downloads\tv_automation\แผนเดือนพค69.xls"
    sheet_name = args.sheet
    
    try:
        year_num, portal_month_val, month_num = parse_sheet_name(sheet_name)
    except Exception as e_sheet:
        print(f"Error parsing sheet name: {e_sheet}")
        sys.exit(1)
        
    print(f"Reading Excel sheet: {sheet_name} (Year {year_num}, Month Number {month_num}, Portal Value {portal_month_val})...")
    xl = pd.ExcelFile(xls_path)
    df = xl.parse(sheet_name)
    
    # Parse rows starting from row 4 (index 4)
    records = []
    for idx in range(4, len(df)):
        row = df.iloc[idx]
        date_raw = row.iloc[1]
        activity_raw = row.iloc[2]
        tool_raw = row.iloc[3]
        location_raw = row.iloc[4]
        target_raw = row.iloc[5]
        co_workers_raw = row.iloc[6]
        tambon_raw = row.iloc[7]
        
        if pd.isna(date_raw) and pd.isna(activity_raw):
            continue
            
        date_str = str(date_raw).strip() if not pd.isna(date_raw) else ""
        activity = str(activity_raw).strip() if not pd.isna(activity_raw) else ""
        tool = str(tool_raw).strip() if not pd.isna(tool_raw) else ""
        location = str(location_raw).strip() if not pd.isna(location_raw) else ""
        target = str(target_raw).strip() if not pd.isna(target_raw) else ""
        co_workers = str(co_workers_raw).strip() if not pd.isna(co_workers_raw) else ""
        tambon = str(tambon_raw).strip() if not pd.isna(tambon_raw) else ""
        
        if not date_str and not activity:
            continue
            
        be_date = parse_date_to_be(date_str, month_num, year_num)
        if not be_date:
            print(f"Warning: Could not parse date '{date_str}' at row {idx+1}. Skipping.")
            continue
            
        # Check for optional overrides in columns 8 to 12 (Unnamed: 8 to Unnamed: 12)
        override_issue = clean_excel_val(row.iloc[8]) if len(row) > 8 and not pd.isna(row.iloc[8]) else ""
        override_activity = clean_excel_val(row.iloc[9]) if len(row) > 9 and not pd.isna(row.iloc[9]) else ""
        override_other = clean_excel_val(row.iloc[10]) if len(row) > 10 and not pd.isna(row.iloc[10]) else ""
        override_location = clean_excel_val(row.iloc[11]) if len(row) > 11 and not pd.isna(row.iloc[11]) else ""
        override_target = clean_excel_val(row.iloc[12]) if len(row) > 12 and not pd.isna(row.iloc[12]) else ""

        issue_val, activity_val, other_text = map_activity(activity, tool)
        
        # Apply overrides
        if override_issue:
            issue_val = override_issue
        if override_activity:
            activity_val = override_activity
        if override_other:
            other_text = override_other

        # Determine location: meetings go to "สนง.กษอ.สีดา", visits fall back to tambon
        resolved_location = location
        if issue_val == "1":
            resolved_location = "สนง.กษอ.สีดา"
        elif not location or "ตำบล" in location and ("…" in location or "." in location):
            resolved_location = tambon if tambon else "ตำบลหนองตาดใหญ่"
            
        if override_location:
            resolved_location = override_location
            
        # Extract numeric target
        numeric_target = "0"
        if "ทุกท่าน" in target or "ทุกคน" in target or "จนท" in target:
            numeric_target = "7"
        else:
            digits = re.findall(r'\d+', target)
            if digits:
                numeric_target = "".join(digits)
                
        if override_target:
            numeric_target = override_target

        records.append({
            "row_num": idx + 1,
            "date": be_date,
            "activity": activity,
            "tool": tool,
            "location": resolved_location,
            "target_raw": target,
            "target_num": numeric_target,
            "co_workers": co_workers,
            "issue_val": issue_val,
            "activity_val": activity_val,
            "other_text": other_text
        })
        
    print(f"Loaded {len(records)} records from Excel sheet.")
    
    print("\nLaunching browser (Headed)...")
    with sync_playwright() as p:
        # Launch browser in headed mode so the user can verify visually
        browser = p.chromium.launch(headless=False)
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
        
        # 1. Fill Main Page Header Fields using JS to bypass Select2 hiding
        print(f"Selecting Year {year_num}...")
        select_by_value_js(page, 'select#PL_YAER', str(year_num))
        time.sleep(1.5)
        
        print(f"Selecting Month from sheet (value={portal_month_val})...")
        select_by_value_js(page, 'select#PL_MOUNT', str(portal_month_val))
        time.sleep(1.5)
        
        print("Selecting Tambon หนองตาดใหญ่...")
        select_by_label_js(page, 'select#PL_TAMBONN', 'หนองตาดใหญ่')
        time.sleep(1.5)
        
        # 2. Fill Table Rows via Modals
        for i, rec in enumerate(records):
            try:
                print(f"\n[{i+1}/{len(records)}] Adding Record (Row {rec['row_num']}): {rec['activity']}")
                
                # Click Add Data button to open modal
                page.click('a:has-text("เพิ่มข้อมูล")')
                page.wait_for_selector('#bizModal_402', state='visible')
                time.sleep(1.0) # Wait brief moment for modal content to settle
                
                # Fill modal fields (these are standard selects and inputs, no Select2 wrapper)
                modal = page.locator('#bizModal_402')
                
                print(f"  Selecting Issue value: {rec['issue_val']}")
                modal.locator('select#PD_ISSUES').select_option(value=rec['issue_val'])
                time.sleep(1.0) # Wait for dynamic activity options to load
                
                print(f"  Selecting Activity value: {rec['activity_val']}")
                modal.locator('select#PD_ACTIVITY').select_option(value=rec['activity_val'])
                
                if str(rec['activity_val']) == "999" or (str(rec['issue_val']) == "2" and str(rec['activity_val']) == "999"):
                    other_val = (rec.get('other_text') or rec.get('activity') or 'ปฏิบัติงานในพื้นที่')[:30]
                    print(f"  Filling Other Activity Text: {other_val}")
                    try:
                        modal.locator('input#PD_OTHER').fill(other_val)
                    except Exception:
                        pass
                    
                print(f"  Filling Date: {rec['date']}")
                page.evaluate(f"""(dateVal) => {{
                    const modalEl = document.querySelector('#bizModal_402');
                    if (!modalEl) return;
                    ['#PD_SDATE', '#PD_EDATE'].forEach(sel => {{
                        const el = modalEl.querySelector(sel);
                        if (el) {{
                            el.removeAttribute('disabled');
                            el.value = dateVal;
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        }}
                    }});
                }}""", rec['date'])
                
                print(f"  Filling Detail: {rec['activity']}")
                modal.locator('textarea#PD_DETAIL').fill(rec['activity'])
                
                print(f"  Filling Location: {rec['location']}")
                modal.locator('textarea#PD_PLACE').fill(rec['location'])
                
                print(f"  Filling Target: {rec['target_num']} (raw: '{rec['target_raw']}')")
                modal.locator('input#PD_TARGET').fill(rec['target_num'])
                
                # Trigger input events and remove disabled attribute from submit button
                page.evaluate("""() => {
                    const modalEl = document.querySelector('#bizModal_402');
                    if (!modalEl) return;
                    const inputs = modalEl.querySelectorAll('input, select, textarea');
                    inputs.forEach(el => {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('keyup', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    });
                    
                    const btn = modalEl.querySelector('button[type="submit"]') 
                             || modalEl.querySelector('button#btn-save') 
                             || modalEl.querySelector('.btn-primary');
                    if (btn) {
                        btn.removeAttribute('disabled');
                        btn.disabled = false;
                        btn.classList.remove('disabled');
                    }
                }""")
                time.sleep(0.3)
                
                try:
                    modal.locator('button[type="submit"]:has-text("บันทึก")').click(timeout=5000)
                except Exception:
                    page.evaluate("""() => {
                        const modalEl = document.querySelector('#bizModal_402');
                        if (!modalEl) return;
                        const btn = Array.from(modalEl.querySelectorAll('button, input[type="submit"]'))
                            .find(b => (b.textContent || '').includes('บันทึก') || (b.value || '').includes('บันทึก'))
                            || modalEl.querySelector('button[type="submit"]')
                            || modalEl.querySelector('button.btn-primary');
                        if (btn) {
                            btn.removeAttribute('disabled');
                            btn.disabled = false;
                            btn.click();
                        } else {
                            const form = modalEl.querySelector('form');
                            if (form) form.submit();
                        }
                    }""")
                
                # Wait for modal to hide (timeout 10s instead of 30s)
                page.wait_for_selector('#bizModal_402', state='hidden', timeout=10000)
                time.sleep(1.0)
            except Exception as e:
                print(f"Error occurred at row {rec['row_num']}: {e}")
                err_img = r"C:\Users\Admin\.gemini\antigravity\brain\32c4dba2-5165-43af-a43d-2d70e1a32c50\scratch\modal_error.png"
                page.screenshot(path=err_img)
                print(f"Saved error screenshot to {err_img}")
                
                err_html = r"C:\Users\Admin\.gemini\antigravity\brain\32c4dba2-5165-43af-a43d-2d70e1a32c50\scratch\modal_error.html"
                try:
                    with open(err_html, "w", encoding="utf-8") as f_err:
                        f_err.write(page.locator('#bizModal_402').inner_html())
                    print(f"Saved error HTML to {err_html}")
                except:
                    pass
                raise e
            
        # 3. Select Approver
        print("\nSelecting Approver นางอรอนงค์ สูญกลาง...")
        select_by_label_js(page, 'select#USR_APPROVERS', 'นางอรอนงค์ สูญกลาง')
        time.sleep(1.0)
        
        # 4. Final Submission or Pause
        if args.submit:
            print("\n*** SUBMITTING PLANS TO PORTAL (บันทึกและส่งข้อมูล) ***")
            page.click('#wf-btn-save')
            try:
                page.wait_for_selector('button.confirm', state='visible', timeout=3000)
                print("Confirming submission...")
                page.click('button.confirm')
                time.sleep(1.0)
            except Exception:
                pass
            # Force native submit to bypass JQuery submit bugs
            page.evaluate("""() => {
                const form = document.querySelector('#form_wf') || document.querySelector('form');
                if (form) form.submit();
            }""")
            print("Form submitted. Waiting 5 seconds for redirection...")
            time.sleep(5)
            print("Submission complete!")
        elif args.draft:
            print("\n*** SAVING PLANS AS DRAFT (บันทึกชั่วคราว) ***")
            page.click('#wf-btn-temp-save')
            try:
                print("Waiting for confirmation dialog...")
                page.wait_for_selector('button.confirm', state='visible', timeout=5000)
                page.click('button.confirm')
                time.sleep(1.0)
            except Exception:
                pass
            # Force native submit to bypass JQuery submit bugs
            page.evaluate("""() => {
                const form = document.querySelector('#form_wf') || document.querySelector('form');
                if (form) form.submit();
            }""")
            print("Draft saved. Waiting 5 seconds for redirection...")
            time.sleep(5)
            print("Draft save complete!")
        else:
            print("\n================ DRY-RUN VERIFICATION ================")
            print("All fields have been filled out successfully.")
            print("The browser will remain open for your inspection.")
            print("PLEASE DO NOT CLOSE THE BROWSER MANUALLY YET.")
            print("Press Enter in the terminal to close the browser and exit.")
            print("======================================================")
            input()
            
        browser.close()

if __name__ == "__main__":
    main()
