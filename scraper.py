import requests
from bs4 import BeautifulSoup
import csv
import time
import sys
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://www.ambitionbox.com/salaries"


def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def get_company_slug(company_name: str) -> str:
    """Convert a company name to its AmbitionBox URL slug."""
    return company_name.strip().lower().replace(" ", "-")


def scrape_page(company_slug: str, page: int) -> list[dict]:
    """Scrape a single page of salary data for a company."""
    url = f"{BASE_URL}/{company_slug}-salaries"
    if page > 1:
        url += f"?page={page}"

    print(f"  Fetching: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=15)

    if resp.status_code == 404:
        print(f"  Company '{company_slug}' not found on AmbitionBox.")
        return []
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tr.jobProfiles-table__row")

    results = []
    for row in rows:
        role_el = row.select_one(".card-content__company")
        role = _clean(role_el.get_text(" ", strip=True)) if role_el else "N/A"

        exp_el = row.select_one(".content-wrapper span")
        experience = _clean(exp_el.get_text(" ", strip=True)) if exp_el else "N/A"

        count_el = row.select_one(".content-wrapper .datapoints")
        num_salaries = _clean(count_el.get_text(" ", strip=True)) if count_el else "N/A"

        salary_el = row.select_one(".salary-range")
        salary_range = _clean(salary_el.get_text(" ", strip=True)) if salary_el else "N/A"

        link_el = row.select_one("td.left-content .card-content a")
        detail_url = ""
        if link_el and link_el.get("href"):
            detail_url = "https://www.ambitionbox.com" + link_el["href"]

        results.append({
            "role": role,
            "experience": experience,
            "num_salaries": num_salaries,
            "salary_range": salary_range,
            "detail_url": detail_url,
        })

    return results


def get_total_pages(company_slug: str) -> int:
    """Get the total number of pages for a company."""
    url = f"{BASE_URL}/{company_slug}-salaries"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code == 404:
        return 0
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    page_links = soup.select("div.pagination-btns a.page")
    if not page_links:
        return 1

    max_page = 1
    for link in page_links:
        text = link.get_text(strip=True)
        if text.isdigit():
            max_page = max(max_page, int(text))
    return max_page


def scrape_company(company_name: str, max_pages: int = 0) -> list[dict]:
    """Scrape all salary data for a company. max_pages=0 means all pages."""
    slug = get_company_slug(company_name)
    print(f"\nScraping salaries for: {company_name} (slug: {slug})")

    total = get_total_pages(slug)
    if total == 0:
        print(f"  No data found for '{company_name}'.")
        return []

    if max_pages > 0:
        total = min(total, max_pages)
    print(f"  Found {total} page(s) of salary data.")

    all_results = []
    for page in range(1, total + 1):
        rows = scrape_page(slug, page)
        for row in rows:
            row["company"] = company_name
        all_results.extend(rows)
        if page < total:
            time.sleep(1.5)  # be polite

    print(f"  Scraped {len(all_results)} roles for {company_name}.")
    return all_results


def save_to_csv(data: list[dict], filename: str):
    """Save scraped data to a CSV file."""
    if not data:
        print("No data to save.")
        return

    fieldnames = ["company", "role", "experience", "salary_range", "num_salaries", "detail_url"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"\nSaved {len(data)} rows to {filename}")


def main():
    # --- CONFIGURE YOUR COMPANIES HERE ---
    companies = [
        "3M",
    ]
    max_pages_per_company = 10  # set to 0 for all pages
    output_file = "salaries.csv"
    # -------------------------------------

    # Or pass companies as command-line args: python scraper.py "TCS" "Infosys" "Google"
    if len(sys.argv) > 1:
        companies = sys.argv[1:]

    all_data = []
    for company in companies:
        data = scrape_company(company, max_pages=max_pages_per_company)
        all_data.extend(data)
        time.sleep(2)  # pause between companies

    save_to_csv(all_data, output_file)


if __name__ == "__main__":
    main()
