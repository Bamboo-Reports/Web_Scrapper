from playwright.sync_api import sync_playwright
import csv
import time

company = "3M"
department = "Engineering - Software & QA"

# ✅ Correct URL format (FIXED)
base_url = "https://www.ambitionbox.com/salaries/3m-salaries/{city}-location?department=engineering-software-qa&page={page}"

# ✅ Predefined cities (stable approach)
cities = [
    ("Bengaluru", "bengaluru"),
    ("Hyderabad", "hyderabad"),
    ("Pune", "pune"),
    ("Mumbai", "mumbai"),
    ("Chennai", "chennai"),
    ("Gurgaon", "gurgaon"),
    ("Noida", "noida")
]

all_data = []

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,   # keep False to avoid blocking
        slow_mo=50
    )

    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )

    page = context.new_page()

    # 🔁 LOOP THROUGH EACH CITY
    for city_name, city_slug in cities:
        print(f"\n===== {city_name} =====")

        page_num = 1

        while True:
            print(f"Scraping page {page_num}...")

            url = base_url.format(city=city_slug, page=page_num)

            try:
                page.goto(url, timeout=60000)
            except:
                print("Blocked or failed. Skipping city.")
                break

            # ✅ Wait for table rows
            try:
                page.wait_for_selector("#designationTable tbody tr", timeout=10000)
            except:
                print("No more data.")
                break

            rows = page.locator("#designationTable tbody tr")
            count = rows.count()

            print("Rows found:", count)

            if count == 0:
                break

            # 🔁 LOOP EACH ROW
            for i in range(count):
                try:
                    row = rows.nth(i)

                    # ✅ ROLE (your exact selector)
                    role = row.locator("td.left-content div a p").inner_text().strip()

                    # ✅ SALARY
                    salary = row.locator("text=₹").first.inner_text().strip()

                    print(city_name, "|", role, "|", salary)

                    all_data.append({
                        "Company": company,
                        "Department": department,
                        "City": city_name,
                        "Role": role,
                        "Salary": salary
                    })

                except:
                    continue

            page_num += 1
            time.sleep(1.5)  # avoid blocking

    browser.close()

# 💾 SAVE TO CSV
if all_data:
    with open("salary_all_cities.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_data[0].keys())
        writer.writeheader()
        writer.writerows(all_data)

    print("\n✅ Data saved successfully in salary_all_cities.csv")
else:
    print("\n❌ No data extracted.")