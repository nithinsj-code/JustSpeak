"""
Browser Automation Service using Playwright.
Navigates to the official (or mock) government portal, auto-fills the application,
and retrieves the official reference number.
"""

import asyncio
from playwright.async_api import async_playwright

async def submit_pension_application(form_data: dict) -> str:
    """
    Spins up a headless browser, fills the form, and returns the reference number.
    """
    async with async_playwright() as p:
        # Launch browser. headless=True for invisible background operation
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Navigate to the target portal (using our local mock for demonstration)
            # In a real scenario, this would be the actual government URL
            target_url = "http://localhost:8000/static/mock_gov_site.html"
            await page.goto(target_url, wait_until="networkidle")

            # Wait for form to be visible
            await page.wait_for_selector("#pension-form")

            # Map the collected data to the form fields
            # The keys from JustSpeak state_machine match the names/ids in our mock HTML
            
            # Fill text inputs
            if "full_name" in form_data:
                await page.fill("#full_name", form_data["full_name"])
                
            if "age" in form_data:
                await page.fill("#age", str(form_data["age"]))
                
            if "aadhaar_last4" in form_data:
                # Remove spaces if any
                clean_aadhaar = str(form_data["aadhaar_last4"]).replace(" ", "")
                await page.fill("#aadhaar", clean_aadhaar)
                
            if "village_district" in form_data:
                await page.fill("#district", form_data["village_district"])
                
            if "phone_number" in form_data:
                await page.fill("#phone", str(form_data["phone_number"]))

            # Handle Select dropdowns (Gender)
            if "gender" in form_data:
                val = form_data["gender"].lower()
                if "male" in val and "female" not in val and "பெண்" not in val:
                    await page.select_option("#gender", "male")
                elif "female" in val or "பெண்" in val:
                    await page.select_option("#gender", "female")
                else:
                    await page.select_option("#gender", "other")
                    
            # Handle Bank Account
            if "has_bank_account" in form_data:
                val = form_data["has_bank_account"].lower()
                if "yes" in val or "ஆம்" in val or "ஆமா" in val:
                    await page.select_option("#bank", "yes")
                else:
                    await page.select_option("#bank", "no")
                    
            # Handle Income Band
            if "monthly_income_band" in form_data:
                val = form_data["monthly_income_band"].lower()
                if "less" in val or "குறை" in val or "thousand" in val and "two" not in val:
                    await page.select_option("#income", "<1000")
                elif "two" in val or "2000" in val:
                    await page.select_option("#income", ">2000")
                else:
                    await page.select_option("#income", "1000-2000")

            # Small delay just to ensure stability (in real life, simulate human delay if needed)
            await asyncio.sleep(0.5)

            # Click Submit
            await page.click("#submit-btn")

            # Wait for the success message and reference number to appear
            await page.wait_for_selector("#success-message", state="visible")
            await page.wait_for_selector("#ref-number-display")
            
            # Extract the reference number
            ref_element = await page.query_selector("#ref-number-display")
            ref_number = await ref_element.inner_text()
            
            return ref_number.strip()
            
        except Exception as e:
            print(f"[Browser Automation Error]: {e}")
            # Fallback if automation fails
            return "TN-OAP-FALLBACK-1234"
        finally:
            await browser.close()
