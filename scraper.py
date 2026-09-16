import json
import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright

URL = "https://www.bain.com/careers/work-with-us/students/nyu-stern/"
EVENTS_FILE = "events.json"
LOGS_FILE = "run_logs.json"

def send_email(subject, body_html):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    recipient = os.environ.get("RECIPIENT_EMAIL")

    if not all([smtp_user, smtp_pass, recipient]):
        print("Missing email credentials. Skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipient, msg.as_string())

def log_run(status, message, event_count=0):
    logs = []
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": status,
        "message": message,
        "total_events_scraped": event_count
    })

    with open(LOGS_FILE, "w") as f:
        json.dump(logs[-100:], f, indent=2)

def main():
    try:
        existing_events = []
        if os.path.exists(EVENTS_FILE):
            try:
                with open(EVENTS_FILE, "r") as f:
                    existing_events = json.load(f)
            except Exception:
                existing_events = []

        existing_ids = {e["id"] for e in existing_events}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="America/New_York"
            )
            page = context.new_page()

            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # Accept cookies if present
            try:
                cookie_btn = page.locator("button:has-text('ACCEPT ALL COOKIES')").first
                if cookie_btn.is_visible(timeout=3000):
                    cookie_btn.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # Expand all events
            while True:
                try:
                    btn = page.locator("button:has-text('Load More'), a:has-text('Load More')").first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        page.wait_for_timeout(2000)
                    else:
                        break
                except Exception:
                    break

            scraped_events = []
            # Target event links directly to locate individual cards precisely
            learn_more_links = page.locator("a:has-text('Learn more')").all()

            for link in learn_more_links:
                try:
                    # Climb up to the specific event card container
                    card = link.locator("xpath=./ancestor::div[contains(@class, 'card') or contains(@class, 'event') or position()=3]").first
                    raw_text = card.inner_text().replace("\xa0", " ")
                    lines = [l.strip() for l in raw_text.split("\n") if l.strip() and l.strip().lower() != "learn more"]

                    if not lines:
                        continue

                    # Extract Date & Title
                    date = "N/A"
                    title = "Unknown Title"
                    
                    # Look for date pattern (e.g. 'Sep 16' or 'Oct 2') in first lines
                    if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+', lines[0], re.IGNORECASE):
                        date = lines[0]
                        title = lines[1] if len(lines) > 1 else "Unknown Title"
                    else:
                        title = lines[0]

                    # Extract Office & Audience metadata
                    office, audience = "N/A", "N/A"
                    for i, line in enumerate(lines):
                        if line.rstrip(":").lower() == "office" and i + 1 < len(lines):
                            val = lines[i + 1]
                            if val.lower() not in ["audience:", "location:"]:
                                office = val
                        elif line.rstrip(":").lower() == "audience" and i + 1 < len(lines):
                            val = lines[i + 1]
                            if val.lower() not in ["office:", "location:"]:
                                audience = val

                    # Get absolute link
                    url = link.get_attribute("href") or URL
                    if url.startswith("/"):
                        url = "https://www.bain.com" + url

                    # Clean ID generation
                    clean_title = re.sub(r'[^a-zA-Z0-9]', '_', title.lower()).strip('_')
                    clean_date = re.sub(r'[^a-zA-Z0-9]', '_', date.lower()).strip('_')
                    unique_id = f"{clean_date}_{clean_title}"

                    scraped_events.append({
                        "id": unique_id,
                        "title": title,
                        "date": date,
                        "office": office,
                        "audience": audience,
                        "url": url
                    })
                except Exception:
                    continue

            browser.close()

        # Deduplicate results
        unique_scraped = {e["id"]: e for e in scraped_events}.values()
        new_events = [e for e in unique_scraped if e["id"] not in existing_ids]

        # Email notification formatted cleanly without descriptions
        if new_events:
            table_rows = "".join([
                f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{e['date']}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;"><strong>{e['title']}</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{e['office']}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{e['audience']}</td>
                    <td style="padding: 8px; border: 1px solid #ddd;"><a href="{e['url']}">View Event</a></td>
                </tr>
                """
                for e in new_events
            ])

            email_body = f"""
            <h2>🚨 {len(new_events)} New Bain Event(s) Posted</h2>
            <table style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
                <thead>
                    <tr style="background-color: #f2f2f2;">
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Date</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Title</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Office</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Audience</th>
                        <th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Link</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            """

            send_email(f"🚨 {len(new_events)} New Bain Event(s) Posted", email_body)

            all_events = list(unique_scraped) + [e for e in existing_events if e["id"] not in {x["id"] for x in unique_scraped}]
            with open(EVENTS_FILE, "w") as f:
                json.dump(all_events, f, indent=2)

        msg = f"Completed run. Scraped {len(unique_scraped)} events ({len(new_events)} new)."
        log_run("SUCCESS", msg, len(unique_scraped))
        print(msg)

    except Exception as e:
        err_msg = f"Execution failed: {str(e)}"
        print(err_msg)
        send_email("❌ FAILURE: Bain Scraper Job", f"<h2>Scraper Error</h2><p>Details: <code>{str(e)}</code></p>")
        log_run("FAILED", err_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
