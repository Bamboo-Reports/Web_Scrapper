import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import sys
import re
import http.cookiejar
import os
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.text import Text


console = Console()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://www.ambitionbox.com/salaries"

# Path to Netscape-format cookies file (exported from browser)
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies-ambitionbox-com.txt")


# --------------- Stats tracker ---------------
class Stats:
    def __init__(self):
        self.start_time = time.time()
        self.total_companies = 0
        self.companies_done = 0
        self.companies_failed = 0
        self.total_pages_fetched = 0
        self.total_roles_found = 0
        self.total_detail_pages = 0
        self.total_rows = 0
        self.total_requests = 0
        self.total_errors = 0
        self.current_company = ""
        self.current_phase = ""
        self.last_url = ""
        self.company_results: list[dict] = []  # per-company summary

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def elapsed_str(self) -> str:
        s = int(self.elapsed)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"

    @property
    def req_per_min(self) -> str:
        if self.elapsed < 1:
            return "..."
        return f"{self.total_requests / self.elapsed * 60:.1f}"

    def build_stats_table(self) -> Table:
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style="bold cyan", min_width=22)
        t.add_column(style="white")
        t.add_column(style="bold cyan", min_width=22)
        t.add_column(style="white")
        t.add_row(
            "Elapsed", self.elapsed_str,
            "Requests", f"{self.total_requests}  ({self.req_per_min}/min)",
        )
        t.add_row(
            "Companies", f"{self.companies_done}/{self.total_companies}  ({self.companies_failed} failed)",
            "Pages fetched", str(self.total_pages_fetched),
        )
        t.add_row(
            "Roles found", str(self.total_roles_found),
            "Detail pages", str(self.total_detail_pages),
        )
        t.add_row(
            "Total rows", str(self.total_rows),
            "Errors", str(self.total_errors),
        )
        return t

    def build_company_table(self) -> Table:
        t = Table(title="Company Results", title_style="bold", show_lines=False)
        t.add_column("#", style="dim", width=4)
        t.add_column("Company", style="bold white", min_width=25)
        t.add_column("Slug", style="dim")
        t.add_column("Pages", justify="right")
        t.add_column("Roles", justify="right")
        t.add_column("Rows", justify="right", style="green")
        t.add_column("Status", justify="center")
        for i, r in enumerate(self.company_results, 1):
            status = "[green]OK[/green]" if r["status"] == "ok" else "[red]FAIL[/red]"
            t.add_row(
                str(i), r["name"], r["slug"],
                str(r["pages"]), str(r["roles"]), str(r["rows"]),
                status,
            )
        return t


STATS = Stats()


# --------------- Session ---------------
SESSION: requests.Session | None = None


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    if os.path.exists(COOKIE_FILE):
        cj = http.cookiejar.MozillaCookieJar()
        cj.load(COOKIE_FILE, ignore_discard=True, ignore_expires=True)
        session.cookies.update(cj)
        console.print(f"[dim]Loaded {len(cj)} cookies from {COOKIE_FILE}[/dim]")
    else:
        console.print(f"[yellow]Warning: Cookie file not found at {COOKIE_FILE}, scraping without auth.[/yellow]")
    return session


def _get_session() -> requests.Session:
    global SESSION
    if SESSION is None:
        SESSION = _make_session()
    return SESSION


def _tracked_get(url: str, **kwargs) -> requests.Response:
    """Wrapper around session.get that tracks request count and errors."""
    STATS.total_requests += 1
    STATS.last_url = url
    try:
        resp = _get_session().get(url, **kwargs)
        if resp.status_code >= 400:
            STATS.total_errors += 1
        return resp
    except requests.RequestException:
        STATS.total_errors += 1
        raise


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------- Slug resolution ---------------
def domain_to_search_term(domain: str) -> str:
    domain = domain.strip().lower()
    domain = re.sub(r'^https?://', '', domain)
    domain = domain.rstrip('/')
    domain = re.sub(r'\.(com|co\.in|in|org|net|io|ai|tech|co|us|uk|de|fr|jp)$', '', domain)
    domain = re.sub(r'^www\.', '', domain)
    return domain


def get_company_slug(company_name: str) -> str:
    return company_name.strip().lower().replace(" ", "-")


def resolve_slug(company_input: str) -> tuple[str, str]:
    if '.' in company_input and ' ' not in company_input:
        search_term = domain_to_search_term(company_input)
    else:
        search_term = company_input

    slug_guess = search_term.strip().lower().replace(" ", "-")

    url = f"{BASE_URL}/{slug_guess}-salaries"
    try:
        resp = _tracked_get(url, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            final_path = resp.url.split('/salaries/')[-1]
            real_slug = final_path.replace('-salaries', '').split('?')[0]
            if real_slug:
                display_name = company_input
                title_match = re.search(r'<title>(.+?)\s+Salar', resp.text)
                if title_match:
                    display_name = title_match.group(1).strip()
                return real_slug, display_name
    except requests.RequestException:
        pass

    return slug_guess, company_input


# --------------- Scraping ---------------
def scrape_page(company_slug: str, page: int) -> list[dict]:
    url = f"{BASE_URL}/{company_slug}-salaries"
    if page > 1:
        url += f"?page={page}"

    resp = _tracked_get(url, timeout=15)

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("tr.jobProfiles-table__row")

    results = []
    for row in rows:
        role_el = row.select_one(".card-content__company")
        role = _clean(role_el.get_text(" ", strip=True)) if role_el else "N/A"
        link_el = row.select_one("td.left-content .card-content a")
        detail_path = link_el["href"] if link_el and link_el.get("href") else ""
        results.append({"role": role, "detail_path": detail_path})

    return results


def _fmt_salary(val) -> str:
    if val is None:
        return ""
    try:
        return f"{float(val) / 100000:.1f}L"
    except (ValueError, TypeError):
        return str(val)


def scrape_role_detail(detail_path: str, company_name: str) -> list[dict]:
    url = f"https://www.ambitionbox.com{detail_path}"
    resp = _tracked_get(url, timeout=15)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text)
    if not m:
        return []

    props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    salary_data = props.get("salaryData", {}).get("data", {})
    if not salary_data:
        return []

    profile = salary_data.get("profileInfo", {})
    summary = salary_data.get("summaryData", {})
    percentiles = summary.get("percentiles", {})

    base_row = {
        "company": company_name,
        "role": profile.get("profileName", ""),
        "num_salaries": summary.get("totalSalaryDataPoints", ""),
        "avg_salary": _fmt_salary(summary.get("totalSalaryAverage")),
        "min_salary": _fmt_salary(summary.get("minCtc")),
        "max_salary": _fmt_salary(summary.get("maxCtc")),
        "median_salary": _fmt_salary(percentiles.get("50.0")),
        "p25_salary": _fmt_salary(percentiles.get("25.0")),
        "p75_salary": _fmt_salary(percentiles.get("75.0")),
        "p90_salary": _fmt_salary(percentiles.get("90.0")),
        "fixed_pct": summary.get("fixedPercent", ""),
        "variable_pct": summary.get("variablePercent", ""),
        "min_exp": summary.get("minExp", ""),
        "max_exp": summary.get("maxExp", ""),
        "detail_url": url,
    }

    for key in ("fixed_pct", "variable_pct"):
        try:
            base_row[key] = f"{float(base_row[key]):.0f}%"
        except (ValueError, TypeError):
            pass

    filters = props.get("filtersData", {})
    locations = filters.get("locationList", [])

    if not locations:
        return [{**base_row, "city": "All India", "city_data_points": base_row["num_salaries"]}]

    rows = []
    rows.append({**base_row, "city": "All India", "city_data_points": base_row["num_salaries"]})
    for loc in locations:
        rows.append({
            **base_row,
            "city": f"{loc.get('name', '')} ({loc.get('state', '')})",
            "city_data_points": loc.get("dataPoints", ""),
        })

    return rows


def get_total_pages(company_slug: str, per_page: int = 20) -> int:
    url = f"{BASE_URL}/{company_slug}-salaries"
    resp = _tracked_get(url, timeout=15)
    if resp.status_code == 404:
        return 0
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    count_els = soup.select(".nav-item__count")
    if count_els:
        count_text = count_els[0].get_text(strip=True)
        count_text = count_text.lower().replace(",", "")
        try:
            if "k" in count_text:
                total_count = int(float(count_text.replace("k", "")) * 1000)
            else:
                total_count = int(count_text)
            if total_count > 0:
                total_pages = (total_count + per_page - 1) // per_page
                return total_pages
        except ValueError:
            pass

    page_links = soup.select("div.pagination-btns a.page")
    if not page_links:
        return 1

    max_page = 1
    for link in page_links:
        text = link.get_text(strip=True)
        if text.isdigit():
            max_page = max(max_page, int(text))
    return max_page


def scrape_company(company_name: str, max_pages: int = 0, fetch_details: bool = True) -> list[dict]:
    """Scrape all salary data for a company with rich progress display."""
    STATS.current_company = company_name
    STATS.current_phase = "Resolving slug..."

    # Resolve
    console.print()
    with console.status(f"[bold cyan]Resolving '{company_name}'...", spinner="dots"):
        slug, display_name = resolve_slug(company_name)
    console.print(f"[bold green]>>>[/] [bold]{display_name}[/] [dim](slug: {slug})[/dim]")

    # Get total pages
    STATS.current_phase = "Counting pages..."
    with console.status("[bold cyan]Counting pages...", spinner="dots"):
        total = get_total_pages(slug)

    if total == 0:
        console.print(f"  [yellow]No data found for '{display_name}'.[/yellow]")
        STATS.companies_failed += 1
        STATS.companies_done += 1
        STATS.company_results.append({
            "name": display_name, "slug": slug, "pages": 0, "roles": 0, "rows": 0, "status": "fail",
        })
        return []

    if max_pages > 0:
        total = min(total, max_pages)

    # Step 1: Collect role links from listing pages
    STATS.current_phase = "Fetching listing pages..."
    role_links = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Listing pages"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[roles]} roles found[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("pages", total=total, roles=0)
        for page in range(1, total + 1):
            rows = scrape_page(slug, page)
            role_links.extend(rows)
            STATS.total_pages_fetched += 1
            STATS.total_roles_found += len(rows)
            progress.update(task, advance=1, roles=len(role_links))
            if page < total:
                time.sleep(1.5)

    console.print(f"  [dim]Found {len(role_links)} roles across {total} page(s)[/dim]")

    if not fetch_details:
        for row in role_links:
            row["company"] = display_name
        STATS.companies_done += 1
        STATS.total_rows += len(role_links)
        STATS.company_results.append({
            "name": display_name, "slug": slug, "pages": total,
            "roles": len(role_links), "rows": len(role_links), "status": "ok",
        })
        return role_links

    # Step 2: Fetch detail pages
    STATS.current_phase = "Fetching role details..."
    all_results = []
    fetchable = [r for r in role_links if r.get("detail_path")]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold magenta]Role details "),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[current]}[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("details", total=len(fetchable), current="")
        for i, role in enumerate(fetchable):
            role_name = role.get("role", "?")
            progress.update(task, current=role_name[:40])
            detail_rows = scrape_role_detail(role["detail_path"], display_name)
            all_results.extend(detail_rows)
            STATS.total_detail_pages += 1
            STATS.total_rows += len(detail_rows)
            progress.update(task, advance=1)
            if i < len(fetchable) - 1:
                time.sleep(1)

    console.print(f"  [green]{len(all_results)} rows[/green] [dim](roles x cities) scraped for {display_name}[/dim]")

    STATS.companies_done += 1
    STATS.company_results.append({
        "name": display_name, "slug": slug, "pages": total,
        "roles": len(fetchable), "rows": len(all_results), "status": "ok",
    })

    return all_results


def save_to_csv(data: list[dict], filename: str):
    if not data:
        console.print("[yellow]No data to save.[/yellow]")
        return

    fieldnames = [
        "company", "role", "city", "city_data_points", "num_salaries",
        "avg_salary", "min_salary", "max_salary",
        "median_salary", "p25_salary", "p75_salary", "p90_salary",
        "fixed_pct", "variable_pct", "min_exp", "max_exp", "detail_url",
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    console.print(f"\n[bold green]Saved {len(data)} rows to {filename}[/bold green]")


def main():
    # --- CONFIGURE YOUR COMPANIES HERE ---
    # Accepts company names ("TCS"), slugs ("tcs"), or domains ("tcs.com")
    companies = [
        "crunchyroll.com",
    ]
    max_pages_per_company = 1  # 0 = all pages
    output_file = "salaries.csv"
    # -------------------------------------

    # Or pass companies as command-line args: python scraper.py "TCS" "Infosys" "Google"
    if len(sys.argv) > 1:
        companies = sys.argv[1:]

    STATS.total_companies = len(companies)

    # Header
    console.print()
    console.print(Panel(
        f"[bold]AmbitionBox Salary Scraper[/bold]\n"
        f"[dim]Companies: {len(companies)} | Max pages/company: {max_pages_per_company or 'all'} | Output: {output_file}[/dim]",
        border_style="cyan",
    ))

    all_data = []
    for idx, company in enumerate(companies, 1):
        console.rule(f"[bold cyan] Company {idx}/{len(companies)}: {company} ", style="cyan")
        try:
            data = scrape_company(company, max_pages=max_pages_per_company)
            all_data.extend(data)
        except Exception as e:
            console.print(f"  [bold red]ERROR:[/bold red] {e}")
            STATS.total_errors += 1
            STATS.companies_failed += 1
            STATS.companies_done += 1
            STATS.company_results.append({
                "name": company, "slug": "?", "pages": 0, "roles": 0, "rows": 0, "status": "fail",
            })

        if idx < len(companies):
            time.sleep(2)

    # Save
    save_to_csv(all_data, output_file)

    # Final summary
    console.print()
    console.rule("[bold green] Final Summary ", style="green")
    console.print()
    console.print(STATS.build_stats_table())
    console.print()
    if STATS.company_results:
        console.print(STATS.build_company_table())
    console.print()
    console.print(Panel(
        f"[bold green]Done![/bold green]  {STATS.total_rows} total rows | "
        f"{STATS.total_requests} requests | {STATS.elapsed_str} elapsed",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
