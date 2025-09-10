import requests
from bs4 import BeautifulSoup
import json

def fetch_ulb_info(url):
    response = requests.get(url)
    response.raise_for_status()  # raise exception if HTTP error
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Adjust these selectors based on the actual HTML structure:
    ulb_table = soup.find('table')  
    if not ulb_table:
        raise ValueError("No table found on page—please verify the page structure.")
    
    rows = ulb_table.find_all('tr')
    headers = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
    data = []
    
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all('td')]
        if len(cells) != len(headers):
            # you may log a warning here
            continue
        data.append(dict(zip(headers, cells)))
    
    return data

def save_to_json(data, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    url = 'https://udhd.jharkhand.gov.in/other/ULBInformation.aspx'
    output_path = 'ulb_info.json'
    
    print(f"Fetching data from: {url}")
    ulb_data = fetch_ulb_info(url)
    
    if not ulb_data:
        print("No data extracted. Please check the page layout.")
        return
    
    save_to_json(ulb_data, output_path)
    print(f"Saved {len(ulb_data)} records to '{output_path}'")

if __name__ == '__main__':
    main()
