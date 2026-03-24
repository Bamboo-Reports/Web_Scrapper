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
            page.wait_for_selector("text=₹", timeout=10000)
        except:
            print("No more data. Ending.")
            break

        time.sleep(3)

        # Scroll
        page.mouse.wheel(0, 12000)
        time.sleep(2)

        # ✅ Find role elements
        roles = page.locator("a")

        count = roles.count()
        print("Total anchors found:", count)

        if count == 0:
            break

        for i in range(count):
            try:
                role_el = roles.nth(i)
                role = role_el.inner_text().strip()

                # 🎯 filter only real job roles
                if not any(k in role for k in ["Engineer", "Lead", "Analyst", "Manager", "Developer"]):
                    continue

                # ✅ correct parent (div based, not tr)
                card = role_el.locator("xpath=ancestor::div[3]")

                text = card.inner_text()

                # extract salary
                salary = next((l for l in text.split("\n") if "₹" in l), None)

                if not salary:
                    continue

                print(role, "|", salary)

                all_data.append({
                    "Company": company,
                    "Department": department,
                    "City": city,
                    "Role": role,
                    "Salary": salary.strip()
                })

            except:
                continue

        page_num += 1
        time.sleep(2)

    browser.close()

# Save
if all_data:
    with open("salary_data3.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_data[0].keys())
        writer.writeheader()
        writer.writerows(all_data)

    print("\n✅ Data saved successfully!")
else:
    print("\n❌ No data extracted.")