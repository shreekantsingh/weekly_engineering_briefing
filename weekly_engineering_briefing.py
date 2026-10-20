#!/usr/bin/env python3
"""Weekly Engineering Digest v3 — stricter relevance and cleaner reporting."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import html, os, re, sys
import requests
import xml.etree.ElementTree as ET

DAYS_BACK = 7
MAX_RESULTS_PER_QUERY = 8
MAX_PER_SECTION = 4
MAX_TOTAL_ITEMS = 15
OUTPUT_FILE = "weekly_engineering_briefing.md"
TIMEOUT_SECONDS = 25
HEADERS = {"User-Agent": "WeeklyEngineeringDigest/3.0 (technical news reader)"}

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
    'cat:cs.NI AND (all:Ethernet OR all:RDMA OR all:congestion OR all:network-fabric)',
    'cat:cs.AR AND (all:interconnect OR all:chiplet OR all:network-on-chip)',
    'cat:eess.SP AND (all:equalization OR all:SerDes OR all:PAM4)',
    'cat:cs.DC AND (all:datacenter AND (all:RDMA OR all:networking OR all:accelerator))',
]

TECH_TERMS = {
    'serdes': 6, 'pam4': 6, '112g': 5, '224g': 5, '448g': 5, 'retimer': 6,
    'signal integrity': 5, 'equalization': 4, 'fec': 3, 'ber': 3, 'channel loss': 4,
    'ethernet': 4, '802.3': 5, 'ieee 802.3': 6, 'oif': 4, 'cei': 4,
    'switch asic': 6, 'networking asic': 6, 'packet buffer': 5, 'roce': 5,
    'infiniband': 4, 'congestion control': 5, 'rdma': 5, 'network fabric': 5,
    'silicon photonics': 5, 'co-packaged optics': 6, 'optical i/o': 6,
    'optical interconnect': 5, 'transceiver': 3, 'chiplet': 4, 'asic': 4,
    'silicon validation': 5, 'firmware': 3, 'sdk compatibility': 5, 'bring-up': 5,
    'hardware verification': 4, 'silicon errata': 5, 'datacenter': 3, 'data center': 3,
    'ai accelerator': 3, 'gpu cluster': 3, 'semiconductor': 1, 'advanced packaging': 4,
    'patent': 2, 'implementation agreement': 4, 'interoperability': 4,
    'network-on-chip': 5, 'network on chip': 5, 'optical i/o': 6,
}
# Reject obviously unrelated paper domains and communications topics outside the user's work.
NEGATIVE_TERMS = [
    'protein', 'genomics', 'clinical', 'medical', 'patient', 'cancer', 'astronomy',
    'galaxy', 'cosmology', 'quantum chemistry', 'agriculture', 'crop', 'animal behavior',
    'linguistics', 'sentiment analysis', 'social media', 'cryptocurrency', 'sports',
    'integrated sensing and communication', 'isac power allocation', 'channel state information',
]
# A paper title must explicitly name one of these core hardware/networking concepts.
PAPER_TITLE_TERMS = (
    'serdes', 'pam4', 'retimer', 'signal integrity', 'equalization', 'ethernet', 'rdma',
    'roce', 'infiniband', 'network fabric', 'network-on-chip', 'network on chip',
    'interconnect', 'chiplet', 'co-packaged optics', 'silicon photonics', 'optical i/o',
    'optical interconnect', 'switch asic', 'networking asic', 'packet buffer',
    'congestion control', 'hardware verification', 'silicon validation', 'firmware',
)
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


def has_term(text, term):
    """Match whole terms/phrases, allowing spaces and hyphens between phrase words."""
    words = re.escape(term).replace(r'\ ', r'[\s-]+')
    return re.search(r'(?<![a-z0-9])' + words + r'(?![a-z0-9])', text, re.I) is not None


def matching_terms(text, terms):
    return [term for term in terms if has_term(text, term)]


def score_item(item):
    title = item['title'].lower()
    body = (title + ' ' + item['summary'].lower())
    if any(has_term(title, term) for term in NEGATIVE_TERMS):
        return 0
    # Exclude low-signal press-release/SEO aggregators seen in test output.
    source = item.get('source', '').lower()
    if any(x in source for x in ('openpr', 'biggo finance', 'biggo.com')):
        return 0
    title_matches = matching_terms(title, TECH_TERMS)
    body_matches = [term for term in matching_terms(body, TECH_TERMS) if term not in title_matches]
    title_score = sum(TECH_TERMS[t] for t in title_matches)
    body_score = sum(min(TECH_TERMS[t], 2) for t in body_matches)
    if item['kind'] == 'paper':
        # Never accept a paper solely because its abstract contains incidental keywords.
        if not any(has_term(title, term) for term in PAPER_TITLE_TERMS):
            return 0
        if title_score < 5:
            return 0
    else:
        # News must have a relevant headline or several distinct signals in the summary.
        if not title_matches and body_score < 7:
            return 0
        if title_score < 3 and body_score < 5:
            return 0
    score = title_score * 2 + body_score
    url = item['url'].lower()
    if any(d.strip() in url for d in PRIMARY_DOMAINS):
        score += 3
    # Down-rank press-release aggregators and thin syndication sites; don't treat them as proof.
    if any(x in source for x in ('newsbreak',)):
        score -= 2
    return score


def classify(item):
    # Classify using the headline first; summaries often contain incidental keywords.
    text = item['title'].lower()
    if any(has_term(text, k) for k in ['serdes', 'pam4', '112g', '224g', '448g', 'retimer', 'equalization', 'signal integrity', 'channel loss', 'cei']):
        return 'SerDes, Signal Integrity & Retimers'
    if any(has_term(text, k) for k in ['co-packaged optics', 'silicon photonics', 'optical i/o', 'optical interconnect', 'transceiver', 'optics', 'vcsel']):
        return 'Optics & Interconnects'
    if any(has_term(text, k) for k in ['ieee', 'oif', 'standard', 'implementation agreement', 'patent', 'interoperability']):
        return 'Standards, Research & Patents'
    if any(has_term(text, k) for k in ['ethernet', 'roce', 'infiniband', 'congestion control', 'network fabric', 'switch', 'rdma', 'networking']):
        return 'Ethernet, Switching & AI Fabrics'
    return 'ASICs, Silicon & Firmware'

def engineering_angle(item):
    title = item['title'].lower()
    parts = []
    if any(has_term(title, k) for k in ['serdes', 'pam4', 'retimer', 'equalization', 'signal integrity', 'channel loss', 'ber']):
        parts.append('For lab relevance, extract lane rate/modulation, channel loss, equalizer/retimer settings, FEC mode and BER or margin results.')
    elif any(has_term(title, k) for k in ['rdma', 'roce', 'ethernet', 'congestion control', 'network fabric', 'switch', 'infiniband']):
        parts.append('For system relevance, identify the topology and traffic pattern, then compare tail latency, throughput, congestion behavior and host/GPU support.')
    elif any(has_term(title, k) for k in ['optical', 'photonics', 'transceiver', 'co-packaged', 'vcsel']):
        parts.append('For link planning, look for reach, power per bit, thermal envelope, serviceability, laser assumptions and measured reliability.')
    elif any(has_term(title, k) for k in ['chiplet', 'asic', 'silicon', 'packaging', 'semiconductor']):
        parts.append('For hardware planning, distinguish working silicon from roadmap claims; look for interface details, yield, thermal limits and availability.')
    elif any(has_term(title, k) for k in ['firmware', 'sdk', 'driver', 'bring-up', 'validation', 'errata']):
        parts.append('For bring-up, record exact hardware revision, SDK/firmware version, known limitations and regression-test coverage.')
    elif item['kind'] == 'paper':
        parts.append('For possible adoption, check whether the paper addresses a real switch/link workload and compare its baselines, hardware and reproducibility.')
    else:
        parts.append('The headline alone is insufficient to infer a design change; read the source for the concrete implementation and evidence.')
    if item['kind'] == 'paper':
        parts.append('Treat results as research evidence, not production validation, until reproduced on comparable hardware.')
    return ' '.join(parts)


def watch_next(item):
    title = item['title'].lower()
    if item['kind'] == 'paper':
        return 'Check the evaluation hardware, workload, baselines, artifacts/code and whether results are reproducible.'
    if any(has_term(title, k) for k in ['standard', 'ieee', 'oif', 'implementation agreement']):
        return 'Verify the official draft/IA number, revision, approval status and interoperability results from the standards body.'
    if any(has_term(title, k) for k in ['launch', 'announced', 'roadmap', 'product', 'release']):
        return 'Look for the vendor datasheet, exact part/revision, availability, supported firmware/SDK and independent measurements.'
    if any(has_term(title, k) for k in ['patent']):
        return 'Check the official publication, independent claims, assignee and legal status before judging technical or commercial scope.'
    return 'Look for primary documentation or measured implementation evidence; do not treat a headline or press release as validation.'


def clean_headline(title, source):
    title = clean(title)
    source = clean(source)
    # Google News often appends the publisher name to the title as a suffix.
    if source:
        title = re.sub(r'\s*(?:[-|–—:]\s*)' + re.escape(source) + r'\s*$', '', title, flags=re.I)
    return title.strip(' -|–—:')

def markdown_to_html(md):
    # Render the simple Markdown emitted by this script without flattening nested lists.
    out = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith('#'):
            if in_list:
                out.append('</ul>'); in_list = False
            n = len(stripped) - len(stripped.lstrip('#'))
            title = html.escape(stripped[n:].strip())
            out.append(f'<h{min(n,3)}>{title}</h{min(n,3)}>')
        elif stripped.startswith('> '):
            if in_list:
                out.append('</ul>'); in_list = False
            out.append('<blockquote>' + inline_md(stripped[2:]) + '</blockquote>')
        elif re.match(r'^\s*[-*]\s+', line):
            if not in_list:
                out.append('<ul>'); in_list = True
            item_text = re.sub(r'^\s*[-*]\s+', '', line)
            out.append('<li>' + inline_md(item_text) + '</li>')
        elif not stripped:
            if in_list:
                out.append('</ul>'); in_list = False
        else:
            if in_list:
                out.append('</ul>'); in_list = False
            out.append('<p>' + inline_md(stripped) + '</p>')
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
    shown = []
    for item in items:
        section = classify(item)
        if section not in grouped or len(grouped[section]) >= MAX_PER_SECTION:
            continue
        grouped[section].append(item)
        shown.append(item)
    lines = [
        '# Weekly Engineering Digest',
        f'_Generated: {generated} | Coverage: previous {DAYS_BACK} days | {len(shown)} items shown_',
        '',
        '> Keyword-curated, not independently fact-checked. Verify primary documentation before making design decisions.',
        '', '## 1. What happened', ''
    ]
    if not shown:
        lines += ['No items passed the relevance and date filters this week. This is preferable to padding the digest with unrelated material.', '']
    for section in sections:
        lines += [f'### {section}', '']
        if not grouped[section]:
            lines += ['_No high-confidence matches this week._', '']
            continue
        for item in grouped[section]:
            date = item['date'].astimezone().strftime('%d %b %Y')
            title = clean_headline(item['title'], item['source']).replace('[', '(').replace(']', ')')
            source = clean(item['source']).replace('[', '(').replace(']', ')')
            kind = 'Research paper' if item['kind'] == 'paper' else 'News'
            lines += [
                f'- **[{title}]({item["url"]})** — {source}, {date} · {kind}',
                f'  **Engineering relevance:** {engineering_angle(item)}',
                f'  **What to verify:** {watch_next(item)}',
            ]
            if item['summary']:
                summary = clean(item['summary'])
                # Avoid repeating the headline verbatim as the entire summary.
                if re.sub(r'[^a-z0-9]+', '', summary.lower()) != re.sub(r'[^a-z0-9]+', '', title.lower()):
                    summary = summary[:240].rstrip()
                    if len(item['summary']) > 240:
                        summary += '…'
                    lines.append(f'  **Source context:** {summary}')
            lines.append('')
    lines += [
        '## 2. Relevance to my work', '',
        '- Highest priority: SerDes/retimers, PAM4 and signal integrity; Ethernet switching and AI fabrics; optical interconnects; ASIC/firmware bring-up and interoperability.',
        '- Before acting on a claim, record exact part/SDK/specification version, test conditions, measured data, BER/failure rate and reproducibility.',
        '- Research results, vendor announcements, roadmap claims, standards drafts and ratified specifications are different evidence classes.',
        '', '## 3. What to watch next', '',
        '- IEEE 802.3 and OIF CEI official revision/status updates and interoperability results.',
        '- Vendor datasheets, silicon errata, SDK/firmware release notes, lab measurements and production availability.',
        '- Reproducible papers and official patent publications tied directly to high-speed links, switches, optical I/O or hardware validation.',
        '', '## Sources and limitations', '',
        '- News discovery: Google News RSS; research discovery: arXiv API with strict title-level relevance checks.',
        '- Publisher links may still pass through Google News when its RSS feed does not expose a clean direct URL.',
        '- Keyword filtering can miss relevant work and cannot independently verify claims or provide exhaustive standards/patent coverage.', ''
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
    print(f'Found {len(found)} raw records; {len(items)} unique items passed filters before section caps.')
    print(f'Saved briefing to {OUTPUT_FILE}')
    send_email(content)

if __name__ == '__main__':
    main()
