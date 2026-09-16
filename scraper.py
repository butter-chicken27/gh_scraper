import json
import os
import smtplib
import sys
from datetime import datetime
from playwright.sync_api import sync_api

URL = "https://www.bain.com/careers/work-with-us/students/nyu-stern/"
EVENTS_FILE = "events.json"
LOGS_FILE = "run_logs.json"

def send_email(subject, body_html):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    recipient = os.environ.get("RECIPIENT_EMAIL")

    if not all([smtp_user, smtp_pass, recipient]):
        print("Missing email credentials. Skipping notification.")
        return

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

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

        with sync_api() as p:
            browser = p.chromium.launch(headless=True)
            
            # --- Stealth & Anti-Detection Setup ---
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768},
                locale="en-US",
                timezone_id="America/New_York"
            )
            page = context.new_page()
            
            # Hide automation flags
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # Dismiss cookie banner if visible
            try:
                cookie_btn = page.locator("button:has-text('ACCEPT ALL COOKIES')").first
                if cookie_btn.is_visible(timeout=3000):
                    cookie_btn.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # Loop through 'Load More'
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

            # Parse Event Cards
            scraped_events = []
            cards = page.locator("div").filter(has=page.locator("a:has-text('Learn more')")).all()

            for card in cards:
                text_lines = [line.strip() for line in card.inner_text().split("\n") if line.strip()]
                link_el = card.locator("a:has-text('Learn more')").first
                url = link_el.get_attribute("href") if link_el.count() > 0 else URL
                if url and url.startswith("/"):
                    url = "https://www.bain.com" + url

                date = text_lines[0] if text_lines else "Unknown Date"
                title = text_lines[1] if len(text_lines) > 1 else "Unknown Title"
                unique_id = f"{date}_{title}".lower().replace(" ", "_")

                office, audience = "N/A", "N/A"
                for i, line in enumerate(text_lines):
                    if line.startswith("Office:") and i + 1 < len(text_lines):
                        office = text_lines[i + 1]
                    if line.startswith("Audience:") and i + 1 < len(text_lines):
                        audience = text_lines[i + 1]

                scraped_events.append({
                    "id": unique_id,
                    "title": title,
                    "date": date,
                    "office": office,
                    "audience": audience,
                    "url": url
                })

            browser.close()

        unique_scraped = {e["id"]: e for e in scraped_events}.values()
        new_events = [e for e in unique_scraped if e["id"] not in existing_ids]

        if new_events:
            items = "".join([f"<li><strong>{e['title']}</strong> ({e['date']}) — <a href='{e['url']}'>Link</a></li>" for e in new_events])
            send_email("🚨 New Bain Event(s) Posted", f"<h2>New Bain NYU Stern Events</h2><ul>{items}</ul>")

            all_events = list(unique_scraped) + [e for e in existing_events if e["id"] not in {x["id"] for x in unique_scraped}]
            with open(EVENTS_FILE, "w") as f:
                json.dump(all_events, f, indent=2)

        msg = f"Completed. Scraped {len(unique_scraped)} events ({len(new_events)} new)."
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
