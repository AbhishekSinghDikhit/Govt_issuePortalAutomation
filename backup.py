from playwright.sync_api import sync_playwright
import base64
from io import BytesIO
from PIL import Image
import pytesseract

def automate_grievance(issue_text="Streetlight not working", 
                       extra_info=False,
                       grievance_location="Main Road, Ranchi",
                       grievance_type="Garbage Collection",
                       grievance_document=None,
                       user_name="Test User",
                       user_mobile="9876543210",
                       user_email="test@example.com"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # ✅ Context with geolocation access allowed
        context = browser.new_context(
            permissions=["geolocation"],
            geolocation={"latitude": 23.36, "longitude": 85.33},  # Ranchi coords
            locale="en-US"
        )
        page = context.new_page()

        # Step 1: Open grievance portal
        page.goto("https://jharkhandegovernance.com/grievance/main", timeout=60000)

        # Step 2: Click 'Register Grievance Now'
        page.get_by_role("button", name="Register Grievance Now").click()

        # Step 3: Acknowledge form
        page.get_by_role("checkbox").click()
        page.wait_for_selector("button:has-text('Continue'):not([disabled])")
        page.get_by_role("button", name="Continue").click()

        # Step 4: Select Parishad
        page.select_option("select[name='ulb']", label="Ranchi Municipal Corporation")
        page.get_by_role("button", name="Next").click()

        # Step 5: Fill grievance description
        page.fill("textarea[name='complaintDescription']", issue_text)
        page.get_by_role("checkbox").click()

        # ✅ Step 6: If extra info required
        if extra_info:
            page.get_by_text("Give More Information").click()  # enable extra section

            if grievance_location:
                page.fill("input[name='grievanceLocation']", grievance_location)

            if grievance_type:
                page.select_option("select[name='problemTypeId']", label=grievance_type)

            if grievance_document:
                page.set_input_files("input[type='file']", grievance_document)

        # Next (after grievance details)
        page.get_by_role("button", name="Next").click()

        # ✅ Step 7: Fill user info
        page.fill("input[name='name']", user_name)
        page.fill("input[name='mobileNo']", user_mobile)
        page.get_by_role("checkbox").click()
        page.fill("input[name='email']", user_email)

        # Next (after personal details)
        page.get_by_role("button", name="Next").click()

        captcha_src = page.locator("img[alt='captcha']").get_attribute("src")
        if captcha_src and captcha_src.startswith("data:image/png;base64,"):
            captcha_base64 = captcha_src.split(",")[1]
            captcha_bytes = base64.b64decode(captcha_base64)

            # Decode with Tesseract OCR
            captcha_img = Image.open(BytesIO(captcha_bytes))
            captcha_text = pytesseract.image_to_string(captcha_img).strip()

            print("🔍 OCR Captcha Guess:", captcha_text)

            # Fill captcha input
            page.fill("input[name='captchaName']", captcha_text)

        else:
            print("⚠️ Could not find captcha image.")

        page.get_by_role("button", name="Submit").click()

        page.wait_for_timeout(5000)
        print("🎉 Grievance submitted successfully")

        browser.close()


if __name__ == "__main__":
    automate_grievance(
        issue_text="Garbage not collected from Sector 7 for 3 days",
        extra_info=True,
        grievance_location="Sector 7, Near Shiv Temple",
        grievance_type="Garbage Collection",
        grievance_document=None,
        user_name="Aditya Singh",
        user_mobile="8463883140",
        user_email="worldforscience@gmail.com"
    )
