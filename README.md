# weekly_engineering_briefing
# Weekly Engineering Digest

Automatically collects recent news and arXiv papers about:
- Networking hardware, SerDes, Ethernet, optical interconnects
- AI infrastructure, data centres and accelerators
- Semiconductors, ASICs and firmware
- Standards, interoperability, research papers and career-relevant developments

It produces a Markdown briefing and emails it through the Resend API every Monday at 09:00 IST.

## Setup

1. Create a GitHub repository and upload:
   - `weekly_engineering_briefing.py`
   - `.github/workflows/weekly-digest.yml`

2. Create a Resend account at https://resend.com/ and create an API key.

3. In the GitHub repository, open **Settings → Secrets and variables → Actions**:
   - Under **Secrets**, add `RESEND_API_KEY` with your Resend API key.
   - Under **Variables**, add `DIGEST_EMAIL` with this recipient address: `shreekant@gmail.com`.
   - Optionally add `DIGEST_FROM` with a sender identity verified in Resend, for example `Engineering Digest <digest@yourdomain.com>`.

4. Sender restrictions:
   - Resend's onboarding sender (`onboarding@resend.dev`) is for testing and may only deliver to the account owner's verified email.
   - For reliable delivery to your own recipient address, verify a domain you control in Resend and set `DIGEST_FROM` to an address on that domain.

5. In GitHub, open **Actions → Weekly Engineering Digest** and enable workflows if prompted.
   Use **Run workflow** to test it immediately.

## Schedule

GitHub Actions cron uses UTC. `30 3 * * 1` means Monday at 09:00 India Standard Time.

## Notes

- The script uses Google News RSS and arXiv. Coverage is not exhaustive.
- The digest's implications and watch items are rule-based prompts, not AI-generated expert conclusions.
- GitHub scheduled workflows can be delayed occasionally, and public repositories may have different usage constraints.
- Never commit API keys into the repository.
