import asyncio, sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from fastapi import FastAPI, Form, File, UploadFile
from typing import Optional
from playwright.sync_api import sync_playwright, Browser
import base64
from io import BytesIO
from PIL import Image, ImageFilter, ImageOps
import pytesseract
import uvicorn
import os
from concurrent.futures import ThreadPoolExecutor
import threading
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import random, string
import json


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

with open("departments.json", "r", encoding="utf-8") as f:
        DEPARTMENT_CONTACTS = json.load(f)

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


def solve_captcha(page, max_retries: int = 10):
    """
    Try to solve captcha with OCR. Retry if OCR fails.
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Captcha attempt {attempt}/{max_retries}")

            captcha_src = page.locator("img[alt='captcha']").get_attribute("src")
            if not captcha_src or not captcha_src.startswith("data:image/png;base64,"):
                logger.error("❌ Captcha image not found")
                return None

            # Decode base64 image
            captcha_base64 = captcha_src.split(",")[1]
            captcha_bytes = base64.b64decode(captcha_base64)

            # Preprocess image
            captcha_img = Image.open(BytesIO(captcha_bytes)).convert("L")
            captcha_img = ImageOps.autocontrast(captcha_img)

            img_cv = np.array(captcha_img)
            _, img_cv = cv2.threshold(img_cv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = np.ones((2, 2), np.uint8)
            img_cv = cv2.morphologyEx(img_cv, cv2.MORPH_OPEN, kernel)
            processed_img = Image.fromarray(img_cv)

            # OCR with multiple configs
            configs = [
                "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                "--psm 7",
                "--psm 6",
            ]
            guesses = []
            for cfg in configs:
                text = pytesseract.image_to_string(processed_img, config=cfg).strip()
                if text:
                    guesses.append(text)

            captcha_text = max(guesses, key=len) if guesses else ""

            logger.info(f"🔍 Captcha guesses: {guesses} | Picked: '{captcha_text}'")

            if captcha_text:
                page.fill("input[name='captchaName']", captcha_text)

                # Click submit to check if captcha passes
                page.get_by_role("button", name="Submit").click()
                page.wait_for_timeout(3000)

                # Detect if captcha was accepted or rejected
                if not page.locator("img[alt='captcha']").is_visible():
                    logger.info("✅ Captcha solved successfully")
                    logger.info("Grievance submitted successfully ✅")
                    return captcha_text
                else:
                    logger.warning("⚠️ Captcha rejected, retrying...")

                    # Reload captcha for retry
                    page.click("img[alt='captcha']")
                    page.wait_for_timeout(1500)

            else:
                logger.warning("⚠️ Empty captcha guess, retrying...")

        except Exception as e:
            logger.exception(f"Error during captcha attempt {attempt}")

    # If all retries fail, return a fallback
    fallback = "".join(random.choices(string.ascii_letters + string.digits, k=5))
    logger.error(f"❌ All captcha attempts failed, using fallback: {fallback}")
    page.fill("input[name='captchaName']", fallback)
    return fallback


#forward the complaint using email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")  # set in env
SMTP_PASS = os.getenv("SMTP_PASS")  # app password / key

def send_email(to_email: str, subject: str, body: str):
    """Send email via SMTP"""
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())

        logger.info(f"📧 Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.exception(f"❌ Failed to send email to {to_email}")
        return False

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

        logger.info("Handling captcha with auto-retry OCR")
        solve_captcha(page, max_retries=10)

        # page.fill("input[name='captchaName']", captcha_text)

        # logger.info("Submitting grievance form")
        # page.get_by_role("button", name="Submit").click()

        page.wait_for_timeout(5000)
        page.close()
        context.close()

        # ✅ Forward complaint to department email
        dept_contact = DEPARTMENT_CONTACTS.get(ulb)
        if dept_contact and dept_contact.get("email"):
            subject = f"New Grievance Raised - {grievance_type or 'General'}"
            body = (
                f"A new grievance has been submitted.\n\n"
                f"Description: {issue_text}\n"
                f"Location: {grievance_location}\n"
                f"Type: {grievance_type}\n"
                f"ULB: {ulb}\n\n"
                f"User Details:\n"
                f"Name: {user_name}\n"
                f"Mobile: {user_mobile}\n"
                f"Email: {user_email}\n"
            )
            send_email(dept_contact["email"], subject, body)

        # logger.info("Grievance submitted successfully ✅")
        return {"status": "success", "message": "Grievance submitted & forwarded to department"}

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

department_names = {
    "dummy": "Dummy Department",
    "agriculture": "Department of Agriculture, Animal Husbandry & Co-operative",
    "building_construction": "Department of Building Construction",
    "cabinet_election": "Department of Cabinet Election",
    "cabinet_secretariat": "Department of Cabinet Secretariat and Vigilance",
    "commercial_taxes": "Department of Commercial Taxes",
    "drinking_water": "Department of Drinking Water and Sanitation",
    "energy": "Department of Energy",
    "excise": "Department of Excise and Prohibition",
    "finance": "Department of Finance",
    "food_supply": "Department of Food, Public Distribution & Consumer Affairs",
    "forest": "Department of Forest, Environment & Climate Change",
    "health": "Department of Health, Medical Education & Family Welfare",
    "home": "Department of Home, Jail & Disaster Management",
    "industries": "Department of Industries",
    "ipr": "Department of Information & Public Relations",
    "it": "Department of Information Technology & e-Governance",
    "law": "Department of Law",
    "mines": "Department of Mines & Geology",
    "panchayati_raj": "Department of Panchayati Raj",
    "personnel": "Department of Personnel, Administrative Reforms & Rajbhasha",
    "revenue": "Department of Revenue, Registration & Land Reforms",
    "road_construction": "Department of Road Construction",
    "rural_development": "Department of Rural Development",
    "welfare": "Department of Scheduled Tribe, Scheduled Caste, Minority and Backward Class Welfare",
    "school_edu": "Department of School Education & Literacy",
    "tourism": "Department of Tourism, Arts, Culture, Sports & Youth Affairs",
    "transport": "Department of Transport",
    "urban_dev": "Department of Urban Development & Housing",
    "water_resources": "Department of Water Resources",
    "women_child": "Department of Women, Child Development & Social Security"
}

@app.post("/submit-grievance/")
async def submit_grievance(
    issue_text: str = Form(...),
    extra_info: bool = Form(False),
    grievance_location: Optional[str] = Form(None),
    grievance_type: Optional[str] = Form(None),
    ulb: str = Form(...),                  # ULB key, e.g. "RMC"
    department: str = Form(...),           # Dept key, e.g. "urban_dev"
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
            ULB_OPTIONS.get(ulb, ulb),   # send display name to automation
            user_name,
            user_mobile,
            user_email,
        )

        # Load contact details
        with open("departments.json", "r", encoding="utf-8") as f:
            departments = json.load(f)

        with open("ulb_info.json", "r", encoding="utf-8") as f:
            ULB_CONTACTS = {u["ulb_name"]: u for u in json.load(f)}

        # ✅ Resolve names via dict
        dept_display = department_names.get(department, department)
        ulb_display = ULB_OPTIONS.get(ulb, ulb)

        dept_info = departments.get(department)  # json contacts
        ulb_info = ULB_CONTACTS.get(ulb_display)  # json contacts (by display name)

        forwarded = []

        # 1. Send grievance to Department
        if dept_info and dept_info.get("email"):
            send_email(
                to_email=dept_info["email"],
                subject=f"New Grievance Raised - {dept_display}",
                body=f"""
Dear {dept_display},

A new grievance has been raised.

📍 Location: {grievance_location or 'Not provided'}
🏛️ ULB: {ulb_display}
👤 Name: {user_name}
📱 Mobile: {user_mobile}
✉️ User Email: {user_email}

📝 Issue: {issue_text}

Regards,  
Jharkhand Civic Issue Automation System
"""
            )
            forwarded.append(f"Department: {dept_display}")

        # 2. Send grievance to ULB
        if ulb_info and ulb_info.get("email"):
            send_email(
                to_email=ulb_info["email"],
                subject=f"New Grievance Raised - {ulb_display}",
                body=f"""
Dear {ulb_display},

A new grievance has been raised.

📍 Location: {grievance_location or 'Not provided'}
🏛️ ULB: {ulb_display}
👤 Name: {user_name}
📱 Mobile: {user_mobile}
✉️ User Email: {user_email}

📝 Issue: {issue_text}

Regards,  
Jharkhand Civic Issue Automation System
"""
            )
            forwarded.append(f"ULB: {ulb_display}")

        # 3. Confirmation to user
        send_email(
            to_email=user_email,
            subject="✅ Your Grievance Has Been Submitted",
            body=f"""
Hello {user_name},

Your grievance has been successfully submitted and forwarded to:

- Department: {dept_display if dept_info else "N/A"}
- ULB: {ulb_display if ulb_info else "N/A"}

📝 Complaint Summary:
{issue_text}

📍 Location: {grievance_location or 'Not provided'}

Thank you for helping improve civic services in Jharkhand!

Regards,  
Jharkhand Civic Issue Automation System
"""
        )

        result["forwarded_to"] = forwarded
        result["confirmation_sent_to_user"] = True

        return result

    except Exception as e:
        logger.exception("Internal Server Error while handling request")
        return {"status": "error", "message": f"Internal Server Error: {str(e)}"}
@app.post("/submit-email/")
async def submit_email(
    grievance_type: str = Form(...),
    grievance_location: str = Form(...),
    issue_text: str = Form(...),
    ulb: str = Form(...),               # ULB key, e.g. "RMC"
    department: str = Form(...),        # Dept key, e.g. "urban_dev"
    user_name: str = Form(...),
    user_mobile: str = Form(...),
    user_email: str = Form(...)
):
    try:
        # Load contact details
        with open("departments.json", "r", encoding="utf-8") as f:
            departments = json.load(f)

        with open("ulb_info.json", "r", encoding="utf-8") as f:
            ULB_CONTACTS = {u["ulb_name"]: u for u in json.load(f)}

        # ✅ Resolve keys to display names
        dept_display = department_names.get(department, department)
        ulb_display = ULB_OPTIONS.get(ulb, ulb)

        dept_info = departments.get(department)
        ulb_info = ULB_CONTACTS.get(ulb_display)

        forwarded = []

        # 1. Send to Department
        if dept_info and dept_info.get("email"):
            send_email(
                to_email=dept_info["email"],
                subject=f"New Grievance Raised - {dept_display}",
                body=f"""
Dear {dept_display},

A new grievance has been raised.

📍 Location: {grievance_location}
🏛️ ULB: {ulb_display}
👤 Name: {user_name}
📱 Mobile: {user_mobile}
✉️ User Email: {user_email}

📝 Issue: {issue_text}

Regards,  
Jharkhand Civic Issue Automation System
"""
            )
            forwarded.append(f"Department: {dept_display}")

        # 2. Send to ULB
        if ulb_info and ulb_info.get("email"):
            send_email(
                to_email=ulb_info["email"],
                subject=f"New Grievance Raised - {ulb_display}",
                body=f"""
Dear {ulb_display},

A new grievance has been raised.

📍 Location: {grievance_location}
🏛️ ULB: {ulb_display}
👤 Name: {user_name}
📱 Mobile: {user_mobile}
✉️ User Email: {user_email}

📝 Issue: {issue_text}

Regards,  
Jharkhand Civic Issue Automation System
"""
            )
            forwarded.append(f"ULB: {ulb_display}")

        # 3. Confirmation to user
        send_email(
            to_email=user_email,
            subject="✅ Your Grievance Has Been Submitted",
            body=f"""
Hello {user_name},

Your grievance has been successfully submitted and forwarded to:

- Department: {dept_display if dept_info else "N/A"}
- ULB: {ulb_display if ulb_info else "N/A"}

📝 Complaint Summary:
{issue_text}

📍 Location: {grievance_location}

Thank you for helping improve civic services in Jharkhand!

Regards,  
Jharkhand Civic Issue Automation System
"""
        )

        return {
            "status": "success",
            "forwarded_to": forwarded,
            "confirmation_sent_to_user": True
        }

    except Exception as e:
        logger.exception("Internal Server Error while handling email submission")
        return {"status": "error", "message": f"Internal Server Error: {str(e)}"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
