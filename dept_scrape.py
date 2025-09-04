import requests
from bs4 import BeautifulSoup
import re
import json

BASE_URL = "https://www.jharkhand.gov.in"
DIR_URL = f"{BASE_URL}/Home/Department"

def fetch_department_links():
    """Scrape the Department Directory page to get names and URLs."""
    resp = requests.get(DIR_URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select("a[href^='/']")  # matches relative paths
    departments = {}
    for a in links:
        name = a.get_text(strip=True)
        url = a["href"]
        if "Department of" in name:
            departments[name] = BASE_URL + url
    return departments

def scrape_contact(url):
    """Scrape contact info (phone, email) from department page."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    phone = email = None

    text = soup.get_text(separator=" ").strip()
    phone_match = re.search(r"Phone(?: No)?:\s*([\d,\s-]+)", text, re.I)
    email_match = re.search(r"Email:\s*([\w\.-]+(?:\[at\]|\@)[\w\.-]+)", text, re.I)

    if phone_match:
        raw_phone = phone_match.group(1)
        # Clean: remove newlines/spaces, collapse multiple commas
        raw_phone = re.sub(r"[\s\n]+", "", raw_phone)
        raw_phone = re.sub(r",+", ",", raw_phone).strip(",")
        # Normalize into list
        phone = [p for p in raw_phone.split(",") if p]

    if email_match:
        email = email_match.group(1).replace("[at]", "@").replace(" ", "")

    return {"phone": phone, "email": email}

if __name__ == "__main__":
    dept_links = fetch_department_links()
    department_contacts = {}

    for name, url in dept_links.items():
        try:
            info = scrape_contact(url)
            if info["phone"] or info["email"]:
                department_contacts[name] = info
        except Exception as e:
            print(f"⚠️ Failed scraping {name}: {e}")

    # ✅ Save to file
    with open("departments.json", "w", encoding="utf-8") as f:
        json.dump(department_contacts, f, indent=4, ensure_ascii=False)

    print("✅ Department contact info saved to departments.json")
