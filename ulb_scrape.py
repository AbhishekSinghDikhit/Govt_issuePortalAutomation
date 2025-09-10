import json
from playwright.sync_api import sync_playwright

def scrape_ulb_info(output_file="ulb_info.json"):
    url = "https://udhd.jharkhand.gov.in/other/ULBInformation.aspx"
    data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)

        # Wait for table
        page.wait_for_selector("table")

        # Get all table rows (skip header row)
        rows = page.query_selector_all("table tr")[1:]

        for row in rows:
            cols = [c.inner_text().strip() for c in row.query_selector_all("td")]
            if len(cols) < 6:
                continue  

            entry = {
                "district": cols[1],
                "ulb_name": cols[2],
                "address": cols[3],
                "email": cols[4],
                "phone": cols[5],
            }
            data.append(entry)

        browser.close()

    # Save JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Scraped {len(data)} ULB records and saved to {output_file}")


if __name__ == "__main__":
    scrape_ulb_info()
