import asyncio, sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from fastapi import FastAPI, Form, File, UploadFile
from typing import Optional
from playwright.sync_api import sync_playwright, Browser
import base64
from io import BytesIO
from PIL import Image
import pytesseract
import uvicorn
import os
from concurrent.futures import ThreadPoolExecutor
import threading

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Jharkhand Grievance Automation API (sync_playwright)")

# Thread pool for running synchronous Playwright code
executor = ThreadPoolExecutor(max_workers=1)  # Single worker to avoid browser conflicts

# Global Playwright/Browser (managed per thread)
thread_local = threading.local()

# to run on localhost
# def get_browser():
#     if not hasattr(thread_local, "playwright"):
#         thread_local.playwright = sync_playwright().start()
#         thread_local.browser = thread_local.playwright.chromium.launch(
#             headless=False, 
#             slow_mo=500     
#         )
#         logger.info("✅ Browser launched successfully in thread")
#     return thread_local.browser

#for deployment
def get_browser():
    if not hasattr(thread_local, "playwright"):
        thread_local.playwright = sync_playwright().start()
        thread_local.browser = thread_local.playwright.chromium.launch(
            headless=True,  
            args=["--no-sandbox", "--disable-dev-shm-usage"]  
        )
        logger.info("✅ Browser launched successfully in thread")
    return thread_local.browser

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting FastAPI application...")
    
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down FastAPI application...")
    try:
        if hasattr(thread_local, "browser") and thread_local.browser:
            thread_local.browser.close()
            logger.info("Browser closed")
        if hasattr(thread_local, "playwright") and thread_local.playwright:
            thread_local.playwright.stop()
            logger.info("Playwright stopped")
        executor.shutdown(wait=True)
        logger.info("Thread pool shutdown")
    except Exception as e:
        logger.exception("Error during shutdown")

def automate_grievance(
    issue_text: str,
    extra_info: bool,
    grievance_location: Optional[str],
    grievance_type: Optional[str],
    ulb: str,  
    user_name: str,
    user_mobile: str,
    user_email: str
):
    browser = get_browser()
    #hardcoded location, we can make it dynamic by fetching user's location
    context = browser.new_context(
        permissions=["geolocation"],
        geolocation={"latitude": 23.36, "longitude": 85.33},  
        locale="en-US"
    )
    page = context.new_page()

    try:
        logger.info("Navigating to grievance portal...")
        page.goto("https://jharkhandegovernance.com/grievance/main", timeout=60000)

        logger.info("Clicking 'Register Grievance Now'")
        page.get_by_role("button", name="Register Grievance Now").click()

        logger.info("Acknowledging form")
        page.get_by_role("checkbox").click()
        page.wait_for_selector("button:has-text('Continue'):not([disabled])")
        page.get_by_role("button", name="Continue").click()

        logger.info(f"Selecting ULB: {ulb}")
        page.select_option("select[name='ulb']", label=ulb)
        page.get_by_role("button", name="Next").click()

        logger.info("Filling grievance description")
        page.fill("textarea[name='complaintDescription']", issue_text)
        page.get_by_role("checkbox").click()

        if extra_info:
            logger.info("Adding extra info")
            page.get_by_text("Give More Information").click()
            if grievance_location:
                page.fill("input[name='grievanceLocation']", grievance_location)
            if grievance_type:
                page.select_option("select[name='problemTypeId']", label=grievance_type)

        page.get_by_role("button", name="Next").click()

        logger.info("Filling user details")
        page.fill("input[name='name']", user_name)
        page.fill("input[name='mobileNo']", user_mobile)
        page.get_by_role("checkbox").click()
        page.fill("input[name='email']", user_email)

        page.get_by_role("button", name="Next").click()

        logger.info("Handling captcha with OCR")
        captcha_src = page.locator("img[alt='captcha']").get_attribute("src")
        if captcha_src and captcha_src.startswith("data:image/png;base64,"):
            captcha_base64 = captcha_src.split(",")[1]
            captcha_bytes = base64.b64decode(captcha_base64)

            captcha_img = Image.open(BytesIO(captcha_bytes))
            captcha_text = pytesseract.image_to_string(captcha_img).strip()

            logger.info(f"🔍 OCR Captcha Guess: {captcha_text}")
            page.fill("input[name='captchaName']", captcha_text)
        else:
            logger.error("Captcha not found on page")
            page.close()
            context.close()
            return {"status": "error", "message": "Captcha not found"}

        logger.info("Submitting grievance form")
        page.get_by_role("button", name="Submit").click()

        page.wait_for_timeout(5000)
        page.close()
        context.close()

        logger.info("Grievance submitted successfully ✅")
        return {"status": "success", "message": "Grievance submitted successfully"}

    except Exception as e:
        logger.exception("Error during grievance automation")
        context.close()
        return {"status": "error", "message": str(e)}

@app.post("/submit-grievance/")
async def submit_grievance(
    issue_text: str = Form(...),
    extra_info: bool = Form(False),
    grievance_location: Optional[str] = Form(None),
    grievance_type: Optional[str] = Form(None),
    ulb: str = Form(...),  
    user_name: str = Form(...),
    user_mobile: str = Form(...),
    user_email: str = Form(...)
):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            automate_grievance,
            issue_text,
            extra_info,
            grievance_location,
            grievance_type,
            ulb, 
            user_name,
            user_mobile,
            user_email,
        )
        return result
    except Exception as e:
        logger.exception("Internal Server Error while handling request")
        return {"status": "error", "message": f"Internal Server Error: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
