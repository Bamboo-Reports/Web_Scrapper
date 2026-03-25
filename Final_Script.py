from playwright.sync_api import sync_playwright
import time
import csv

company = "3M"
department = "Engineering - Software & QA"
city = "Bengaluru"

base_url = "https://www.ambitionbox.com/salaries/3m-salaries/bengaluru-location?department=engineering-software-qa&page={}"

all_data = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page_num = 1

    while True:
        print(f"\nScraping page {page_num}...")

        page.goto(base_url.format(page_num))

        try:
            page.wait_for_selector("#designationTable tbody tr", timeout=10000)
        except:
            print("No more data. Ending.")
            break

        time.sleep(3)

        rows = page.locator("#designationTable tbody tr")
        count = rows.count()

        print("Rows found:", count)

        if count == 0:
            break

        for i in range(count):
            try:
                row = rows.nth(i)

                # ✅ ROLE (designation)
                role = row.locator("td.left-content a p").inner_text().strip()

                # ✅ SALARY
                salary = row.locator("text=₹").first.inner_text().strip()

                print(role, "|", salary)

                all_data.append({
                    "Company": company,
                    "Department": department,
                    "City": city,
                    "Role": role,
                    "Salary": salary
                })

            except:
                continue

        page_num += 1
        time.sleep(2)

    browser.close()

# Save to CSV
if all_data:
    with open("salary_data4.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_data[0].keys())
        writer.writeheader()
        writer.writerows(all_data)

    print("\n✅ Data saved successfully!")
else:
    print("\n❌ No data extracted.")
