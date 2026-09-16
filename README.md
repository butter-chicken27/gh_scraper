# Automated Event Web Scraper & Alert System

An automated, serverless web scraper built with Python and Playwright that monitors event listings, logs run statuses, and sends real-time email notifications when new events are detected. It uses GitHub Actions alongside an external webhook service for reliable, scheduled execution on free-tier infrastructure.

---

## Features

- **Headless Browser Automation**: Powered by Playwright with stealth configurations to bypass basic bot detection (`navigator.webdriver` removal, realistic user-agents, viewport sizing).
- **Automated Workflow Orchestration**: Scheduled execution via GitHub Actions (`repository_dispatch`, `schedule`, `workflow_dispatch`).
- **High-Precision External Webhook Triggers**: Direct triggers via `cron-job.org` using GitHub Fine-Grained Personal Access Tokens (PATs) to bypass internal queue delays.
- **State Tracking & Persistence**: Automatically maintains persistent JSON state files (`events.json`, `run_logs.json`) back to the GitHub repository.
- **Instant Email Alerts**: Sends structured HTML email alerts via Gmail SMTP whenever newly posted events are detected or job failures occur.
- **Robust Execution Logging**: Keeps a rolling execution log of the last 100 runs with timestamps, statuses, and scraped event counts.

---

## Tech Stack & Tools

* **Core Scraper:** Python 3.10+, Playwright
* **Automation Platform:** GitHub Actions
* **Trigger Mechanism:** Cron-job.org (Webhook `POST` triggers)
* **Notification System:** Python `smtplib` / `email.mime` (Gmail SMTP with App Passwords)
* **Data Storage:** JSON-based persistence (`events.json`, `run_logs.json`)

---

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── scraper.yml         # GitHub Actions workflow configuration
├── events.json                 # Persistent database of tracked unique event IDs
├── run_logs.json               # Rolling history log of script execution runs
├── requirements.txt            # Python dependencies (playwright)
├── scraper.py                  # Main scraping, parsing, logging & email script
└── README.md                   # System documentation
```

---

## Setup & Configuration Guide

### 1. Configure Repository Secrets

Navigate to **Settings** > **Secrets and variables** > **Actions** in your GitHub repository and add the following repository secrets:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `SMTP_USER` | Sending Gmail address | `yourname@gmail.com` |
| `SMTP_PASS` | Google 16-character App Password | `xxxx xxxx xxxx xxxx` |
| `RECIPIENT_EMAIL` | Destination email address for alerts | `user@domain.com` |

---

### 2. Create a Fine-Grained Personal Access Token (PAT)

To enable external webhook triggers via `repository_dispatch`:

1. Navigate to **Developer Settings** > **Personal Access Tokens** > **Fine-grained tokens**.
2. Click **Generate new token**.
3. Under **Repository Access**, select **Only select repositories** and pick your scraper repository.
4. Expand **Permissions** > **Repository permissions**.
5. Set **Contents** to **Read and write**.
6. Generate the token and save the output key (`github_pat_...`).

---

### 3. Configure External Webhook Trigger (Cron-job.org)

To bypass default GitHub Actions scheduling queue variances and run tasks on exact time intervals:

1. Create a free account on [cron-job.org](https://cron-job.org).
2. Click **Create Cronjob** and configure the endpoint URL:  
   `https://api.github.com/repos/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/dispatches`
3. Set the HTTP Request Method to **POST**.
4. Configure the following HTTP headers:

| Header Name | Value |
| :--- | :--- |
| `Authorization` | `Bearer YOUR_FINE_GRAINED_PAT` |
| `User-Agent` | `CronJob` |
| `Accept` | `application/vnd.github.v3+json` |
| `Content-Type` | `application/json` |

5. Add the JSON request body payload:
```json
{"event_type": "trigger-scraper"}
```
6. Set your desired execution frequency (e.g., every 15 minutes or 1 minute for testing).

---

## Workflow Logic & Data Flow

1. **Trigger**: `cron-job.org` sends an authenticated `POST` request to GitHub's `repository_dispatch` API endpoint.
2. **Provisioning**: GitHub Actions spins up an `ubuntu-latest` runner, checks out the repo, sets up Python 3.10, and installs Playwright with Chromium binaries.
3. **Scraping Execution**: `scraper.py` launches a headless Chromium instance with stealth overrides, navigates to the target URL, dynamically expands content lists, and extracts event links and titles.
4. **ID Generation & Deduplication**: Unique event identifiers are derived from event URLs/parameters. The script filters newly extracted events against existing IDs recorded in `events.json`.
5. **Alert Distribution**:
   - If new events are found, an HTML email summary is dispatched via Gmail SMTP, and `events.json` is updated.
   - If execution fails at any point, a failure notification with detailed traceback is emailed immediately.
6. **Logging & Persistence**: Execution metadata is recorded in `run_logs.json`. Updated JSON files are automatically committed back to the main branch by `github-actions[bot]`.

---

## Local Development & Testing

1. **Clone the repository**:
   ```bash
   git clone https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git
   cd YOUR_REPO_NAME
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Set environment variables**:
   ```bash
   export SMTP_USER="yourname@gmail.com"
   export SMTP_PASS="xxxx xxxx xxxx xxxx"
   export RECIPIENT_EMAIL="user@domain.com"
   ```

4. **Execute script manually**:
   ```bash
   python scraper.py
   ```
