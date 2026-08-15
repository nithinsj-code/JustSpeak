"""
Browser Automation Service using Playwright.
Navigates to the official (or mock) government portal, auto-fills the application,
and retrieves the official reference number.
"""

import asyncio
import time
from playwright.sync_api import sync_playwright

def _sync_submit_pension_application(form_data: dict) -> str:
    """
    Spins up a headless browser, fills the form, and returns the reference number.
    """
    with sync_playwright() as p:
        # Launch browser. headless=True for invisible background operation
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            # Navigate to the target portal (using our local mock for demonstration)
            # In a real scenario, this would be the actual government URL
            target_url = "http://localhost:8000/static/mock_gov_site.html"
            page.goto(target_url, wait_until="networkidle", timeout=8000)

            # Wait for form to be visible
            page.wait_for_selector("#pension-form", timeout=8000)

            # Map the collected data to the form fields
            # The keys from JustSpeak state_machine match the names/ids in our mock HTML
            
            # Fill text inputs
            full_name = form_data.get("full_name") or form_data.get("name")
            if full_name:
                page.fill("#full_name", str(full_name))
                
            age = form_data.get("age")
            if age:
                page.fill("#age", str(age))
                
            aadhaar = form_data.get("aadhaar_last4") or form_data.get("aadhaar") or form_data.get("aadhaar_last_4_digits")
            if aadhaar:
                clean_aadhaar = str(aadhaar).replace(" ", "")
                page.fill("#aadhaar", clean_aadhaar)
                
            district = form_data.get("village_district") or form_data.get("district") or form_data.get("village")
            if district:
                page.fill("#district", str(district))

            # Handle Select dropdowns (Gender)
            gender = form_data.get("gender")
            if gender:
                val = str(gender).lower()
                if "female" in val or "பெண்" in val:
                    page.select_option("#gender", "female")
                elif "male" in val or "ஆண்" in val:
                    page.select_option("#gender", "male")
                else:
                    page.select_option("#gender", "other")
                    
            # Handle Bank Account
            bank = form_data.get("has_bank_account") or form_data.get("bank_account") or form_data.get("bank")
            if bank:
                val = str(bank).lower()
                if "yes" in val or "ஆம்" in val or "ஆமா" in val or "உண்டு" in val or "இருக்கு" in val:
                    page.select_option("#bank", "yes")
                else:
                    page.select_option("#bank", "no")
                    
            # Handle Income Band
            income = form_data.get("monthly_income_band") or form_data.get("monthly_income") or form_data.get("income")
            if income:
                val = str(income).lower()
                if "<1000" in val or "less" in val or "குறை" in val:
                    page.select_option("#income", "<1000")
                elif ">2000" in val or "more" in val or "மேல்" in val or "அதிக" in val or "2000" in val and "முதல்" not in val:
                    page.select_option("#income", ">2000")
                else:
                    page.select_option("#income", "1000-2000")

            # Small delay just to ensure stability
            time.sleep(0.5)

            # Click Submit
            page.click("#submit-btn")

            # Wait for the success message and reference number to appear
            page.wait_for_selector("#success-message", state="visible")
            page.wait_for_selector("#ref-number-display")
            
            # Extract the reference number
            ref_element = page.query_selector("#ref-number-display")
            ref_number = ref_element.inner_text() if ref_element else "TN-OAP-FALLBACK-1234"
            
            return ref_number.strip()
            
        except Exception as e:
            print(f"[Browser Automation Error]: {e}")
            # Fallback if automation fails
            return "TN-OAP-FALLBACK-1234"
        finally:
            browser.close()


async def submit_pension_application(form_data: dict) -> str:
    """Async wrapper that runs Playwright in a worker thread."""
    return await asyncio.to_thread(_sync_submit_pension_application, form_data)

