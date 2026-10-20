#!/usr/bin/env python3
"""Weekly Engineering Digest v2 — targeted engineering news and arXiv papers."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import html, os, re, sys
import requests
import xml.etree.ElementTree as ET

DAYS_BACK = 7
MAX_RESULTS_PER_QUERY = 10
MAX_PER_SECTION = 5
MAX_TOTAL_ITEMS = 18
OUTPUT_FILE = "weekly_engineering_briefing.md"
TIMEOUT_SECONDS = 25
HEADERS = {"User-Agent": "WeeklyEngineeringDigest/2.0 (technical news reader)"}

# Searches are deliberately narrow. The relevance gate below is applied after retrieval.
NEWS_QUERIES = {
    "SerDes, Signal Integrity & Retimers": [
        'SerDes PAM4 112G 224G 448G retimer signal integrity BER equalization',
        'OIF CEI electrical interface implementation agreement 224G 448G',
        'high speed interconnect channel loss FEC DSP receiver transmitter validation',
    ],
    "Ethernet, Switching & AI Fabrics": [
        'IEEE 802.3 Ethernet 800G 1.6T switch ASIC networking',
        'AI cluster Ethernet fabric RoCE congestion control scale up scale out',
        'data center switch silicon network processor packet buffer telemetry',
    ],
    "Optics & Interconnects": [
        'co-packaged optics CPO optical I/O silicon photonics datacenter switch',
        'optical interconnect laser reliability pluggable transceiver 800G 1.6T',
    ],
    "ASICs, Silicon & Firmware": [
        'networking ASIC silicon validation bring-up errata firmware SDK compatibility',
        'semiconductor chiplet advanced packaging yield high speed I/O',
        'HPE Juniper Cisco Broadcom Marvell Arista networking silicon product announcement',
    ],
    "Standards, Research & Patents": [
        'site:ieee.org 802.3 Ethernet working group project',
        'site:oiforum.com CEI Ethernet interconnect implementation agreement',
        'patent SerDes retimer PAM4 Ethernet optical interconnect',
    ],
}

# arXiv is queried only in relevant technical categories; a second gate checks the title/abstract.
ARXIV_QUERIES = [
    'cat:cs.NI AND (all:Ethernet OR all:networking OR all:congestion OR all:datacenter)',
    'cat:cs.AR AND (all:interconnect OR all:chiplet OR all:NoC OR all:network-on-chip)',
    'cat:eess.SP AND (all:equalization OR all:signal-integrity OR all:SerDes OR all:PAM4)',
    'cat:cs.DC AND (all:datacenter OR all:RDMA OR all:network-fabric OR all:accelerator)',
    'cat:cs.PF AND (all:hardware OR all:ASIC OR all:firmware OR all:verification)',
]

TECH_TERMS = {
    'serdes': 5, 'pam4': 5, '112g': 5, '224g': 5, '448g': 5, 'retimer': 5,
    'signal integrity': 4, 'equalization': 4, 'fec': 3, 'ber': 3, 'channel loss': 4,
    'ethernet': 3, '802.3': 4, 'ieee 802.3': 5, 'oif': 3, 'cei': 3,
    'switch asic': 5, 'networking asic': 5, 'packet buffer': 4, 'roce': 4,
    'infiniband': 3, 'congestion control': 4, 'rdma': 3, 'network fabric': 4,
    'silicon photonics': 4, 'co-packaged optics': 5, 'optical i/o': 5,
    'optical interconnect': 4, 'transceiver': 2, 'chiplet': 3, 'asic': 3,
    'silicon validation': 4, 'firmware': 2, 'sdk compatibility': 4, 'bring-up': 4,
    'hardware verification': 3, 'silicon errata': 4, 'datacenter': 2, 'data center': 2,
    'ai accelerator': 2, 'gpu cluster': 2, 'semiconductor': 1, 'advanced packaging': 3,
    'patent': 1, 'implementation agreement': 3, 'interoperability': 3,
}
NEGATIVE_TERMS = [
    'protein', 'genomics', 'clinical', 'medical', 'patient', 'cancer', 'astronomy',
    'galaxy', 'cosmology', 'quantum chemistry', 'agriculture', 'crop', 'animal behavior',
    'linguistics', 'sentiment analysis', 'social media', 'cryptocurrency', 'sports',
]
PRIMARY_DOMAINS = (
    'ieee.org', 'oiforum.com', 'ethernetalliance.org', 'arxiv.org', 'ietf.org',
    'broadcom.com', 'marvell.com', 'intel.com', 'amd.com', 'nvidia.com', ' juniper.net',
    'hpe.com', 'cisco.com', 'arista.com', 'keysight.com', 'teledynelecroy.com',
    'semtech.com', 'asteralabs.com', 'synopsys.com', 'cadence.com', 'imec-int.com',
)


def clean(value):
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))
    return re.sub(r'\s+', ' ', value).strip()


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_news(query):
    url = 'https://news.google.com/rss/search?q=' + quote(f'{query} when:{DAYS_BACK}d') + '&hl=en-US&gl=US&ceid=US:en'
    out = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for node in root.findall('.//item')[:MAX_RESULTS_PER_QUERY]:
            title = clean(node.findtext('title'))
            link = (node.findtext('link') or '').strip()
            date = parse_date(node.findtext('pubDate'))
            summary = clean(node.findtext('description'))
            source_node = node.find('source')
            source = clean(source_node.text) if source_node is not None else 'Google News'
            if title and link and date:
                out.append({'title': title, 'url': link, 'date': date, 'summary': summary,
                            'source': source, 'kind': 'news'})
    except Exception as exc:
        print(f'Warning: news query failed: {query}: {exc}', file=sys.stderr)
    return out


def fetch_arxiv(query):
    url = 'https://export.arxiv.org/api/query?search_query=' + quote(query) + '&start=0&max_results=12&sortBy=submittedDate&sortOrder=descending'
    out = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        for entry in root.findall('a:entry', ns):
            title = clean(entry.findtext('a:title', default='', namespaces=ns))
            link = next((n.attrib.get('href', '') for n in entry.findall('a:link', ns)
                         if n.attrib.get('rel') == 'alternate'), '')
            date = parse_date(entry.findtext('a:published', default='', namespaces=ns))
            summary = clean(entry.findtext('a:summary', default='', namespaces=ns))
            if title and link and date:
                out.append({'title': title, 'url': link, 'date': date, 'summary': summary,
                            'source': 'arXiv', 'kind': 'paper'})
    except Exception as exc:
        print(f'Warning: arXiv query failed: {query}: {exc}', file=sys.stderr)
    return out


def score_item(item):
    title = item['title'].lower()
    body = (title + ' ' + item['summary'].lower())
    if any(term in title for term in NEGATIVE_TERMS):
        return 0
    # Papers need a clearly relevant title, not merely a passing mention in the abstract.
    title_score = sum(weight for term, weight in TECH_TERMS.items() if term in title)
    body_score = sum(min(weight, 2) for term, weight in TECH_TERMS.items() if term in body and term not in title)
    score = title_score * 2 + body_score
    if item['kind'] == 'paper' and title_score < 3:
        return 0
    if item['kind'] == 'news' and title_score == 0:
        # Keep only news with several relevant signals in the summary.
        if body_score < 5:
            return 0
    if any(d in item['url'].lower() for d in PRIMARY_DOMAINS):
        score += 2
    return score


def classify(item):
    text = (item['title'] + ' ' + item['summary']).lower()
    if any(k in text for k in ['serdes', 'pam4', '112g', '224g', '448g', 'retimer', 'equalization', 'signal integrity', 'channel loss', 'cei']):
        return 'SerDes, Signal Integrity & Retimers'
    if any(k in text for k in ['co-packaged optics', 'silicon photonics', 'optical i/o', 'optical interconnect', 'transceiver', 'optics']):
        return 'Optics & Interconnects'
    if any(k in text for k in ['ieee', 'oif', 'standard', 'implementation agreement', 'patent', 'interoperability']):
        return 'Standards, Research & Patents'
    if any(k in text for k in ['ethernet', 'roce', 'infiniband', 'congestion control', 'network fabric', 'switch', 'rdma', 'networking']):
        return 'Ethernet, Switching & AI Fabrics'
    return 'ASICs, Silicon & Firmware'


def engineering_angle(item):
    text = (item['title'] + ' ' + item['summary']).lower()
    points = []
    if any(k in text for k in ['serdes', 'pam4', 'retimer', 'equalization', 'signal integrity', 'channel loss', 'ber']):
        points.append('Check lane rate/modulation, channel assumptions, equalizer or DSP details, FEC/BER targets, and margin across PVT.')
    if any(k in text for k in ['ethernet', 'roce', 'infiniband', 'congestion', 'switch', 'rdma', 'network fabric']):
        points.append('Check topology, latency/throughput measurements, congestion behavior, interoperability and the relevant protocol revision.')
    if any(k in text for k in ['optical', 'photonics', 'transceiver', 'co-packaged']):
        points.append('Check power per bit, reach, thermal constraints, laser/serviceability assumptions and measured link reliability.')
    if any(k in text for k in ['asic', 'chiplet', 'semiconductor', 'packaging', 'silicon']):
        points.append('Check silicon/package availability, interface details, yield or thermal constraints, and whether claims are measured or roadmap-only.')
    if any(k in text for k in ['firmware', 'sdk', 'driver', 'bring-up', 'validation', 'errata']):
        points.append('Check affected hardware/SDK versions, known limitations, regression coverage and reproducibility of the reported behavior.')
    if item['kind'] == 'paper':
        points.append('For the paper, inspect its evaluation setup, baselines, artifacts/code, and whether results generalize beyond the tested workload.')
    return ' '.join(points[:2]) or 'Open the source and identify the concrete specification, measurement, implementation status, or design decision affected.'


def watch_next(item):
    text = (item['title'] + ' ' + item['summary']).lower()
    checks = []
    if any(k in text for k in ['standard', 'ieee', 'oif', 'implementation agreement']):
        checks.append('Look for the draft/version number, ballot or ratification status, and interoperability evidence.')
    if any(k in text for k in ['launch', 'announced', 'roadmap', 'product', 'release']):
        checks.append('Look for a datasheet, availability date, firmware/SDK support and independent measurements.')
    if item['kind'] == 'paper':
        checks.append('Look for code/data, follow-up work, and replication on comparable hardware or workloads.')
    if 'patent' in text:
        checks.append('Check the official publication, claims, assignee, and prosecution/status details before judging practical scope.')
    if not checks:
        checks.append('Track primary documentation and measured implementation evidence before treating this as a design input.')
    return ' '.join(checks)


def markdown_to_html(md):
    # Small dependency-free Markdown subset: headings, paragraphs, bullets and links.
    out = []
    in_list = False
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith('#'):
            if in_list:
                out.append('</ul>'); in_list = False
            n = len(line) - len(line.lstrip('#'))
            title = html.escape(line[n:].strip())
            out.append(f'<h{min(n,3)}>{title}</h{min(n,3)}>')
        elif line.startswith('- '):
            if not in_list:
                out.append('<ul>'); in_list = True
            out.append('<li>' + inline_md(line[2:]) + '</li>')
        elif not line.strip():
            if in_list:
                out.append('</ul>'); in_list = False
        else:
            if in_list:
                out.append('</ul>'); in_list = False
            out.append('<p>' + inline_md(line) + '</p>')
    if in_list:
        out.append('</ul>')
    return '<html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto;line-height:1.55;color:#222">' + ''.join(out) + '</body></html>'


def inline_md(s):
    # Escape first; then render only the limited syntax emitted by this script.
    s = html.escape(s, quote=True)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^ )]+)\)', r'<a href="\2">\1</a>', s)
    return s


def build_report(items, generated):
    sections = list(NEWS_QUERIES.keys())
    grouped = {section: [] for section in sections}
    for item in items:
        section = classify(item)
        if section not in grouped:
            section = 'ASICs, Silicon & Firmware'
        if len(grouped[section]) < MAX_PER_SECTION:
            grouped[section].append(item)
    lines = [
        '# Weekly Engineering Digest',
        f'_Generated: {generated} | Coverage: previous {DAYS_BACK} days | {len(items)} qualified unique items_',
        '',
        '> Curated keyword-based digest, not an independently verified assessment. Treat vendor claims as claims; confirm primary documentation before design decisions.',
        '', '## 1. What happened', ''
    ]
    if not items:
        lines += ['No items passed the relevance and date filters this week. This is preferable to filling the digest with unrelated papers.', '']
    for section in sections:
        lines += [f'### {section}', '']
        if not grouped[section]:
            lines += ['_No high-confidence matches this week._', '']
            continue
        for item in grouped[section]:
            date = item['date'].astimezone().strftime('%d %b %Y')
            title = item['title'].replace('[', '(').replace(']', ')')
            source = item['source'].replace('[', '(').replace(']', ')')
            lines += [
                f'- **[{title}]({item["url"]})** — {source}, {date} · {"Research paper" if item["kind"] == "paper" else "News"}',
                f'  - **Engineering angle:** {engineering_angle(item)}',
                f'  - **What to verify next:** {watch_next(item)}',
            ]
            if item['summary']:
                summary = item['summary'][:360].rstrip()
                if len(item['summary']) > 360:
                    summary += '…'
                lines.append(f'  - **Source context:** {summary}')
            lines.append('')
    lines += [
        '## 2. Relevance to my work', '',
        '- Highest priority: high-speed SerDes/retimers, PAM4 and signal integrity; Ethernet switching and AI fabrics; optical interconnects; ASIC/firmware bring-up and interoperability.',
        '- For each candidate change, capture the exact part/SDK/specification version, test conditions, measured data, failure rate or BER, and reproducibility before acting.',
        '- Distinguish a research result, vendor announcement, roadmap claim, standards draft, and ratified specification; they are not equivalent evidence.',
        '', '## 3. What to watch next', '',
        '- IEEE 802.3 and OIF CEI status changes, drafts/agreements and interoperability results.',
        '- Public datasheets, silicon errata, SDK/firmware release notes, lab measurements and production availability.',
        '- Reproducible papers and patent publications directly tied to high-speed links, switches, optical I/O or hardware validation.',
        '', '## Sources and limitations', '',
        '- News discovery: Google News RSS. Research discovery: arXiv API restricted to relevant computing/electrical-engineering categories plus title relevance checks.',
        '- Duplicate headlines are removed and each item is placed in one section only. Keyword filtering can still miss important stories or admit borderline ones.',
        '- This script does not verify factual accuracy, infer business impact, or provide exhaustive standards/patent coverage.', ''
    ]
    return '\n'.join(lines)


def send_email(content):
    api_key = os.getenv('RESEND_API_KEY')
    recipient = os.getenv('DIGEST_EMAIL')
    sender = os.getenv('DIGEST_FROM', 'Weekly Engineering Digest <onboarding@resend.dev>')
    if not api_key or not recipient:
        print('Email not sent: RESEND_API_KEY and DIGEST_EMAIL must be configured.')
        return
    payload = {
        'from': sender, 'to': [recipient],
        'subject': f'Weekly Engineering Digest — {datetime.now().astimezone().strftime("%d %b %Y")}',
        'text': content, 'html': markdown_to_html(content),
    }
    r = requests.post('https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload, timeout=TIMEOUT_SECONDS)
    if not r.ok:
        raise RuntimeError(f'Resend API returned HTTP {r.status_code}: {r.text[:500]}')
    print(f'Email accepted by Resend for delivery to {recipient}. Response: {r.text[:250]}')


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    found = []
    print('Collecting targeted engineering news...')
    for section, queries in NEWS_QUERIES.items():
        print(f'  {section}')
        for query in queries:
            found.extend(fetch_news(query))
    print('Collecting relevant arXiv papers...')
    for query in ARXIV_QUERIES:
        found.extend(fetch_arxiv(query))

    # Normalize and deduplicate by title; retain the highest scoring version.
    unique = {}
    for item in found:
        if not item['date'] or item['date'] < cutoff or item['date'] > datetime.now(timezone.utc) + timedelta(hours=12):
            continue
        score = score_item(item)
        if score < 5:
            continue
        item['score'] = score
        key = re.sub(r'[^a-z0-9]+', '', item['title'].lower())
        if not key:
            continue
        if key not in unique or item['score'] > unique[key]['score']:
            unique[key] = item
    items = sorted(unique.values(), key=lambda x: (x['score'], x['date']), reverse=True)[:MAX_TOTAL_ITEMS]
    generated = datetime.now().astimezone().strftime('%d %b %Y, %H:%M %Z')
    content = build_report(items, generated)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Found {len(found)} raw records; {len(items)} unique items passed filters.')
    print(f'Saved briefing to {OUTPUT_FILE}')
    send_email(content)

if __name__ == '__main__':
    main()
