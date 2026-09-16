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
      "total_events_scraped": event_count,
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
          user_agent=(
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
          ),
          viewport={"width": 1366, "height": 768},
          locale="en-US",
          timezone_id="America/New_York",
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
          btn = page.locator(
              "button:has-text('Load More'), a:has-text('Load More')"
          ).first
          if btn.is_visible(timeout=2000):
            btn.click()
            page.wait_for_timeout(2000)
          else:
            break
        except Exception:
          break

      # Extract Title and URL directly from card elements
      extracted_cards = page.evaluate("""() => {
                const results = [];
                const links = Array.from(document.querySelectorAll('a')).filter(
                    a => a.innerText.trim().toLowerCase() === 'learn more'
                );

                links.forEach(link => {
                    let container = link.closest('.card, .event, [class*="card"], [class*="event"]') || 
                                    link.parentElement.parentElement.parentElement;

                    if (!container) return;

                    const text = container.innerText || '';
                    const lines = text.split('\\n')
                                      .map(s => s.trim())
                                      .filter(s => s.length > 0 && s.toLowerCase() !== 'learn more');

                    let title = "Unknown Title";
                    if (lines.length > 0) {
                        // Skip date lines (e.g. 'Sep 16') to grab actual title
                        if (/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+\\d+/i.test(lines[0]) && lines.length > 1) {
                            title = lines[1];
                        } else {
                            title = lines[0];
                        }
                    }

                    results.push({
                        title: title,
                        url: link.href
                    });
                });
                return results;
            }""")

      scraped_events = []
      for item in extracted_cards:
        title = item["title"]
        url = item["url"]

        # Generate unique ID based on URL/eventid (allows same-title events)
        event_id_match = re.search(r"eventid=(\d+)", url, re.IGNORECASE)
        if event_id_match:
          unique_id = f"event_{event_id_match.group(1)}"
        else:
          unique_id = re.sub(r"[^a-zA-Z0-9]", "_", url.lower()).strip("_")

        scraped_events.append({
            "id": unique_id,
            "title": title,
            "url": url,
        })

      browser.close()

    # Match new events using URL unique IDs
    new_events = [e for e in scraped_events if e["id"] not in existing_ids]

    if new_events:
      list_items = "".join([
          f"<li style='margin-bottom: 12px;'><strong>{e['title']}</strong><br><a"
          f" href='{e['url']}'>View Event Details</a></li>"
          for e in new_events
      ])

      email_body = f"""
            <h2>🚨 {len(new_events)} New Bain Event(s) Posted</h2>
            <ul style="font-family: Arial, sans-serif; line-height: 1.5; padding-left: 20px;">
                {list_items}
            </ul>
            """

      send_email(
          f"🚨 {len(new_events)} New Bain Event(s) Posted", email_body
      )

      # Store full list of all active scraped events
      all_events = scraped_events + [
          e
          for e in existing_events
          if e["id"] not in {x["id"] for x in scraped_events}
      ]
      with open(EVENTS_FILE, "w") as f:
        json.dump(all_events, f, indent=2)

    msg = (
        f"Completed run. Scraped {len(scraped_events)} total events"
        f" ({len(new_events)} new)."
    )
    log_run("SUCCESS", msg, len(scraped_events))
    print(msg)

  except Exception as e:
    err_msg = f"Execution failed: {str(e)}"
    print(err_msg)
    send_email(
        "❌ FAILURE: Bain Scraper Job",
        f"<h2>Scraper Error</h2><p>Details: <code>{str(e)}</code></p>",
    )
    log_run("FAILED", err_msg)
    sys.exit(1)


if __name__ == "__main__":
  main()
