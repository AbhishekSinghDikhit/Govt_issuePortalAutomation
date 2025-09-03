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
from fastapi.middleware.cors import CORSMiddleware

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Jharkhand Grievance Automation API (sync_playwright)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["https://your-frontend-domain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

#ulb options
ULB_OPTIONS = {
    "JNP1": "Jugsalai Nagar Parishad",
    "BNP": "Bansidhar Nagar Panchayat",
    "BSNP": "Barki Saraiya Nagar Panchayat",
    "UDHD": "UD&HD",
    "NUNP": "Nagar Untari Nagar Panchayat",
    "RMC": "Ranchi Municipal Corporation",
    "SNP": "Simdega Nagar Parishad",
    "BNP2": "Barharwa Nagar Panchayat",
    "MNP1": "Mihijham Nagar Parishad",
    "PNP1": "Phusro Nagar Parishad",
    "BNP3": "Bachra Nagar Panchayat",
    "MMC": "Medininagar Municipal Corporation",
    "HNP": "Hariharganj Nagar Panchayat",
    "SNP2": "Sahibganj Nagar Parishad",
    "MNP2": "Mahagama Nagar Panchayat",
    "DNP1": "Domchach Nagar Panchayat",
    "MNP3": "Madhupur Nagar Parishad",
    "RNP": "Ramgarh Nagar Parishad",
    "CNP1": "Chattarpur Nagar Panchayat",
    "PNP2": "Pakur Nagar Parishad",
    "BNP4": "Badakisarai Nagar Panchayat",
    "KNP": "Kapali Nagar Parishad",
    "MMC2": "Mango Municipal Corporation",
    "RNP2": "Rajmahal Nagar Panchayat",
    "MNP4": "Manjhiaon Nagar Panchayat",
    "SNP3": "Saraikela Nagar Panchayat",
    "DNP2": "Dhanwar Nagar Panchayat",
    "DNP3": "Dumka Nagar Parishad",
    "DMC": "Dhanbad Municipal Corporation",
    "LNP": "Lohardaga Nagar Parishad",
    "JM": "Jugsalai Municipality",
    "GNP1": "Garhwa Nagar Parishad",
    "JNC": "Jamshedpur NAC",
    "JNP2": "Jhumritilaiya Nagar Parishad",
    "GMC": "Giridih Municipal Corporation",
    "KNP2": "Khunti Nagar Panchayat",
    "LNP2": "Latehar Nagar Panchayat",
    "GNP2": "Gumla Nagar Parishad",
    "HNP2": "Hussainabad Nagar Panchayat",
    "KNP3": "Koderma Nagar Panchayat",
    "GNP3": "Godda Nagar Parishad",
    "HMC": "Hazaribagh Municipal Corporation",
    "JNP3": "Jamtara Nagar Panchayat",
    "BNP5": "Bishrampur Nagar Parishad",
    "BNP6": "Bundu Nagar Panchayat",
    "AMC": "Adityapur Municipal Corporation",
    "CNP2": "Chaibasa Nagar Parishad",
    "CNP3": "Chirkunda Nagar Parishad",
    "CNP4": "Chatra Nagar Parishad",
    "DNN": "Deoghar Nagar Nigam",
    "CMC": "Chas Municipal Corporation",
    "BNP7": "Basukinath Nagar Panchayat",
    "CNP5": "Chakradharpur Nagar Parishad",
    "CNP6": "Chakulia Nagar Panchayat",
}

#grievance issue types
ISSUE_TYPES = {
    "TD": "Test Demo",
    "TC": "TEST CASE",
    "ELHP": "Electricity connection in LHP",
    "FNR": "Fund not received",
    "PMAY": "PMAY (LHP) Handover",
    "HYDT": "HYDT REPARING",
    "MR": "Motor Repairing",
    "NBRI": "New Boring Related Issue (HYDT/MINI HYDT)",
    "WBI": "Water Bill Related Issue",
    "HPR": "Hand Pump Repairing",
    "WLL": "Water Line Leakage",
    "ST": "SEPTIC TANK",
    "RNB": "R & B Related Issues",
    "NHTL": "New Holding and Trade licence",
    "NTLR": "New Trade licence and renewal",
    "TRI": "Tax increase related issue",
    "HTNG": "Applied but holding or trade number not generated",
    "BPR": "Bill Paid online but receipt not generated",
    "WNE": "Wrong Name In Bill/Error in Spelling/Address Change/Phone number change",
    "TEST": "test",
    "TRI2": "Tax related information",
    "TR": "Tax Reduction",
    "PVC": "Property Vacant/Closed",
    "PTU": "Property Tax-Application done but not resolved",
    "NOT": "Name/Occupier Transfer",
    "MR2": "Measurement Related",
    "DR": "Discount Related",
    "BNR": "Bill Not Received",
    "COT": "Change of Owner/Tenant",
    "CIP": "Change In Purpose (Residential/commercial)",
    "DIC": "Drain Is Fully Clogged",
    "IDG": "Issue of Dump garbage",
    "NWT": "Need Water Tanker",
    "SNR": "Sweeping not done on road",
    "DTV": "Door-To-Door Vehicle Not Comming",
    "DC": "Drain Cleaning",
    "CPT": "Cleaning Of Public Toilets",
    "GC": "Grass Cutting",
    "RC": "Road Cleaning",
    "DA": "Dead Animal",
    "GC2": "Garbage Collection",
    "CI": "Cleaning Issue",
    "HMLR": "High Mast Light repairing",
    "NSLI": "New Street Light Installation",
    "SLR": "Street Light Repairing",
    "CWDB": "To Capture The Wandering Dogs And biting dog",
    "TSD": "Treatment of ill / sick Dogs",
    "CRD": "To Capture rabies dogs",
    "CSV": "Capture stray dogs for Sterilization And Vaccination",
    "MI": "Mosquito Infestation",
    "RFP": "Regarding Fogging Perfomance",
    "CRT": "Clear the road by cutting fallen trees",
    "TCT": "Trimming / Cutting the trees branches on road side",
    "DW": "Drain work",
    "RW": "Road work",
    "DMCM": "Drainage- Manhole Cover Missing",
    "RWL": "Road-Waterlogged Due To Rain",
    "RO": "Road-Other",
    "MHR": "Manhole Repairing",
    "MCR": "Manhole Cover Repairing",
    "FR": "Footpath Renovation",
    "IA": "Illegal Activity",
    "PRB": "Public Road Blocked",
    "IS": "Illegal Store",
    "IC": "Illegal Construction",
    "IVP": "Illegal Vehicle Parking",
    "IPF": "ILLEGAL PIG FARMING",
    "ICW": "Illegal connection of water from RMC water tank",
    "ODI": "Open Defecation issue",
    "OUI": "Open urination issue",
    "IL": "Issue of litring",
    "ICC": "Illegal Construction of cow shed",
    "WBM": "Waste Building Materials on public road",
    "IDGR": "Issue of Dump garbage on road",
    "IBG": "Issue of burning garbage",
    "IDGP": "Issue of Dump garbage in pond",
    "SUP": "Single use plastic issue",
    "NDB": "No Dustbin in business places",
    "BPB": "Banned plastic bag issue",
    "CMR": "Construction material is on the roadside",
    "VCTA": "violation of Cigarettes and Other Tobacco Products Act",
    "EF": "Encroachment free",
    "SUP2": "Single Use Plastic",
    "SUH": "Shelters for Urban Homeless",
    "SUV": "Support to Urban strret Vendors",
    "ANW": "Application is not Working",
    "CMI": "When my certificate will issue",
    "DN": "Documents needed",
    "WCL": "Why certificate is late",
    "BDR": "Regarding Birth/Death Registration",
}


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
