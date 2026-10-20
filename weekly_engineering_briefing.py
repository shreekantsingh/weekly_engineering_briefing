#!/usr/bin/env python3
"""
Weekly Engineering Briefing
Runs in Google Colab or any online Python environment.

Collects recent stories from Google News RSS and arXiv, filters to the past
7 days, removes duplicates, and writes a Markdown briefing with source links.
No API key is required. Headlines/snippets are source material, not verified
technical conclusions; open the linked sources before making design decisions.
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import re
import requests
import xml.etree.ElementTree as ET
import os
import html

DAYS_BACK = 7
MAX_ITEMS_PER_QUERY = 12
OUTPUT_FILE = "weekly_engineering_briefing.md"
TIMEOUT_SECONDS = 20

QUERIES = {
    "Networking, SerDes & Ethernet": [
        '"SerDes" OR "PAM4" OR "112G" OR "224G" Ethernet',
        'Ethernet standards IEEE 802.3 networking hardware',
        'optical interconnect silicon photonics co-packaged optics',
        'Ethernet switch ASIC network processor firmware',
    ],
    "AI Infrastructure & Data Centres": [
        'AI data center networking scale-up scale-out fabric',
        'AI accelerator interconnect Ethernet InfiniBand',
        'data centre power cooling high-speed networking',
    ],
    "Semiconductors, ASICs & Firmware": [
        'ASIC semiconductor chiplet advanced packaging',
        'firmware hardware bring-up silicon validation',
        'semiconductor process technology foundry roadmap',
    ],
    "Standards, Research & Career": [
        'IEEE Ethernet standards working group announcement',
        'OIF CEI standards implementation agreement SerDes',
        'networking hardware research paper patent',
        'engineering conference call for papers networking silicon',
    ],
}

ARXIV_QUERIES = [
    'all:Ethernet AND (all:networking OR all:datacenter)',
    'all:optical interconnect OR all:silicon photonics',
    'all:SerDes OR all:PAM4 OR all:chiplet',
    'all:AI accelerator AND all:interconnect',
]

HEADERS = {"User-Agent": "WeeklyEngineeringBriefing/1.0 (RSS reader)"}


def clean_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"&amp;", "&", value)
    value = re.sub(r"&lt;", "<", value)
    value = re.sub(r"&gt;", ">", value)
    value = re.sub(r"&quot;", '"', value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None


def fetch_google_news(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(f"{query} when:{DAYS_BACK}d")
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    items = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        for node in root.findall(".//item")[:MAX_ITEMS_PER_QUERY]:
            title = clean_html(node.findtext("title"))
            link = node.findtext("link", "").strip()
            pubdate = parse_date(node.findtext("pubDate"))
            description = clean_html(node.findtext("description"))
            source_node = node.find("source")
            source = clean_html(source_node.text) if source_node is not None else "Google News"
            if title and link:
                items.append({
                    "title": title, "url": link, "date": pubdate,
                    "summary": description, "source": source, "kind": "news"
                })
    except Exception as exc:
        print(f"  Warning: Google News query failed ({query}): {exc}")
    return items


def fetch_arxiv(query):
    url = (
        "https://export.arxiv.org/api/query?search_query="
        + quote(query)
        + "&start=0&max_results=8&sortBy=submittedDate&sortOrder=descending"
    )
    items = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title = clean_html(entry.findtext("a:title", default="", namespaces=ns))
            link = ""
            for link_node in entry.findall("a:link", ns):
                if link_node.attrib.get("rel") == "alternate":
                    link = link_node.attrib.get("href", "")
                    break
            date = parse_date(entry.findtext("a:published", default="", namespaces=ns))
            summary = clean_html(entry.findtext("a:summary", default="", namespaces=ns))
            if title and link:
                items.append({
                    "title": title, "url": link, "date": date,
                    "summary": summary, "source": "arXiv", "kind": "paper"
                })
    except Exception as exc:
        print(f"  Warning: arXiv query failed ({query}): {exc}")
    return items


def why_it_matters(item, section):
    text = (item["title"] + " " + item["summary"]).lower()
    cues = []
    if any(k in text for k in ["serdes", "pam4", "112g", "224g", "signal integrity", "equalization"]):
        cues.append("Potential implications for link margin, channel loss, equalization, BER, validation and bring-up.")
    if any(k in text for k in ["ethernet", "802.3", "switch", "routing", "congestion", "roce"]):
        cues.append("May affect interoperability, network architecture, performance, or implementation choices.")
    if any(k in text for k in ["ai accelerator", "gpu", "data center", "datacenter", "scale-up", "scale-out"]):
        cues.append("Could influence AI-cluster topology, bandwidth, latency, power, cooling or total system cost.")
    if any(k in text for k in ["asic", "chiplet", "packaging", "silicon", "foundry"]):
        cues.append("Could change silicon integration, package constraints, yield, supply-chain risk or product roadmaps.")
    if any(k in text for k in ["firmware", "driver", "validation", "debug", "bring-up"]):
        cues.append("Relevant to firmware compatibility, lab workflows, failure isolation and silicon validation.")
    if any(k in text for k in ["standard", "ieee", "oif", "specification", "interoperability"]):
        cues.append("Check the specification status and implementation details before treating it as a design requirement.")
    if item["kind"] == "paper":
        cues.append("Research result: inspect the paper's assumptions, test setup, baselines and reproducibility before applying it.")
    if not cues:
        cues.append(f"Potentially relevant to {section.lower()}; inspect the source for concrete technical details.")
    return " ".join(dict.fromkeys(cues))


def watch_next(item):
    text = (item["title"] + " " + item["summary"]).lower()
    checks = []
    if any(k in text for k in ["standard", "ieee", "oif", "specification"]):
        checks.append("Look for the next standards draft, ballot, interoperability event or implementation agreement.")
    if any(k in text for k in ["product", "launch", "roadmap", "announced", "release"]):
        checks.append("Watch for datasheets, availability dates, measured performance and independent validation.")
    if item["kind"] == "paper":
        checks.append("Watch for follow-up work, public code/data, and results from independent implementations.")
    if any(k in text for k in ["patent", "patented"]):
        checks.append("Check the patent's claims, filing/publication status and practical implementation scope.")
    if not checks:
        checks.append("Look for primary documentation, measured results, standards status and evidence of real-world adoption.")
    return " ".join(dict.fromkeys(checks))


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    all_items = []
    print("Collecting recent news and research...")
    for section, queries in QUERIES.items():
        print(f"  {section}")
        for query in queries:
            all_items.extend(fetch_google_news(query))
    print("  Research papers (arXiv)")
    for query in ARXIV_QUERIES:
        all_items.extend(fetch_arxiv(query))

    # Deduplicate by normalized title, retain only dated items in the requested window.
    unique = {}
    for item in all_items:
        if not item["date"] or item["date"] < cutoff:
            continue
        key = re.sub(r"[^a-z0-9]+", "", item["title"].lower())
        if key and key not in unique:
            unique[key] = item
    items = sorted(unique.values(), key=lambda x: x["date"], reverse=True)

    generated = datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
    lines = [
        "# Weekly Engineering Briefing",
        f"_Generated: {generated} · Coverage: previous {DAYS_BACK} days_",
        "",
        "> This script collects headlines and abstracts; it does not independently verify claims or generate human-level technical analysis. Open primary sources before making engineering decisions.",
        "",
        "## 1. What happened",
        "",
    ]
    if not items:
        lines += ["No dated items were retrieved. Check your internet connection or try again later.", ""]
    else:
        for section in QUERIES:
            section_items = []
            for item in items:
                text = (item["title"] + " " + item["summary"]).lower()
                # Lightweight keyword routing to keep the report readable.
                keywords = {
                    "Networking, SerDes & Ethernet": ["serdes", "pam4", "ethernet", "802.3", "optical", "photonics", "switch", "network", "interconnect", "oif"],
                    "AI Infrastructure & Data Centres": ["ai", "accelerator", "gpu", "data center", "datacenter", "scale-up", "scale-out", "infiniband", "roce"],
                    "Semiconductors, ASICs & Firmware": ["asic", "chip", "silicon", "semiconductor", "firmware", "driver", "validation", "foundry", "packaging"],
                    "Standards, Research & Career": ["standard", "ieee", "oif", "arxiv", "patent", "paper", "conference", "research", "interoperability"],
                }[section]
                if any(k in text for k in keywords):
                    section_items.append(item)
            lines += [f"### {section}", ""]
            if not section_items:
                lines += ["_No matching items found this week._", ""]
            for item in section_items[:10]:
                date = item["date"].astimezone().strftime("%d %b %Y")
                lines += [
                    f"- **[{item['title']}]({item['url']})** — {item['source']}, {date}",
                    f"  - **Why it matters:** {why_it_matters(item, section)}",
                    f"  - **What to watch next:** {watch_next(item)}",
                ]
                if item["summary"]:
                    snippet = item["summary"][:420].rstrip()
                    if len(item["summary"]) > 420:
                        snippet += "…"
                    lines.append(f"  - **Source summary:** {snippet}")
                lines.append("")

    lines += [
        "## 2. Why it matters for my work",
        "",
        "- Prioritize items that affect link budgets, signal integrity, BER, firmware/SDK compatibility, interoperability, validation strategy, or architecture decisions.",
        "- For any proposed design change, confirm the source specification/version, operating conditions, test method and measured results.",
        "",
        "## 3. What to watch next",
        "",
        "- New IEEE 802.3 and OIF drafts/agreements, interoperability events and public implementation updates.",
        "- Vendor datasheets, firmware/SDK releases, silicon errata, measured performance and availability dates.",
        "- New conference papers, patent publications and reproducible results relevant to high-speed links and AI fabrics.",
        "",
        "## Sources and limitations",
        "",
        "- News is discovered through Google News RSS; research papers are discovered through arXiv.",
        "- Patent and standards coverage is not exhaustive. For formal decisions, search the relevant standards body and patent database directly.",
        "- The 'Why it matters' and 'What to watch next' bullets are rule-based prompts, not claims that the event will necessarily affect your specific design.",
        "",
    ]
    content = "\n".join(lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nDone. Found {len(items)} unique dated items.")
    print(f"Saved briefing to: {OUTPUT_FILE}")
    print("\nPreview:\n")
    print(content[:9000])

    # Optional email delivery. Configure RESEND_API_KEY and DIGEST_EMAIL.
    api_key = os.getenv("RESEND_API_KEY")
    recipient = os.getenv("DIGEST_EMAIL")
    sender = os.getenv("DIGEST_FROM", "Weekly Engineering Digest <onboarding@resend.dev>")
    if api_key and recipient:
        # Render Markdown as readable plain text and a simple HTML email.
        # The Markdown report remains attached as a .md file via a separate link in logs.
        plain_text = content
        escaped = html.escape(content)
        html_body = (
            "<div style='font-family:Arial,sans-serif;max-width:900px;margin:auto;"
            "line-height:1.55;white-space:pre-wrap'>" + escaped + "</div>"
        )
        try:
            mail_response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "from": sender,
                    "to": [recipient],
                    "subject": f"Weekly Engineering Digest — {datetime.now().astimezone().strftime('%d %b %Y')}",
                    "text": plain_text,
                    "html": html_body,
                },
                timeout=TIMEOUT_SECONDS,
            )
            mail_response.raise_for_status()
            print(f"Email sent successfully to {recipient}.")
        except Exception as exc:
            print(f"ERROR: Email delivery failed: {exc}")
            raise
    else:
        print("Email not sent: set RESEND_API_KEY and DIGEST_EMAIL environment variables.")


if __name__ == "__main__":
    main()
