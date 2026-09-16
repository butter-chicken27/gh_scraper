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

            # Robust Browser-Native Card Extraction
            extracted_cards = page.evaluate("""() => {
                const results = [];
                const links = Array.from(document.querySelectorAll('a')).filter(
                    a => a.innerText.trim().toLowerCase() === 'learn more'
                );

                links.forEach(link => {
                    // Traverse up to find the self-contained event container element
                    let container = link.closest('.card, .event, [class*="card"], [class*="event"]') || 
                                    link.parentElement.parentElement.parentElement;

                    if (!container) return;

                    const text = container.innerText || '';
                    const lines = text.split('\\n')
                                      .map(s => s.trim())
                                      .filter(s => s.length > 0 && s.toLowerCase() !== 'learn more');

                    results.push({
                        lines: lines,
                        url: link.href
                    });
                });
                return results;
            }""")

            scraped_events = []
            for item in extracted_cards:
                lines = item["lines"]
                url = item["url"]
                if not lines:
                    continue

                # Parse Date & Title
                date = "N/A"
                title = "Unknown Title"

                if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+', lines[0], re.IGNORECASE):
                    date = lines[0]
                    title = lines[1] if len(lines) > 1 else "Unknown Title"
                else:
                    title = lines[0]

                # Parse Office & Audience
                office, audience = "N/A", "N/A"
                for i, line in enumerate(lines):
                    clean_line = line.rstrip(":").strip().lower()
                    if clean_line == "office" and i + 1 < len(lines):
                        office = lines[i + 1]
                    elif clean_line == "audience" and i + 1 < len(lines):
                        audience = lines[i + 1]

                # Generate clean unique ID
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

            browser.close()
