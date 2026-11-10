# Moving the site to a custom domain

The site currently lives at `https://tushar-mahalya.github.io/archlens/`. Every internal link,
asset, and script is relative, so the same files work there and at a domain root. Only the
absolute URLs listed in step 5 must change. Do not add a `CNAME` file before the domain is
bought and configured. (This repository deploys with a GitHub Actions workflow, so GitHub ignores
a `CNAME` file anyway; the domain is set in the repository settings.)

## Option A: a custom domain, such as `archlens.sh`

1. Buy the domain from any registrar.
2. In the repository, open **Settings → Pages → Custom domain**, enter the domain, and save.
   Do this before you create DNS records, so nobody else can claim the domain on GitHub Pages.
   Optionally verify the domain in your account's Pages settings for extra takeover protection.
3. At the registrar, create DNS records. These values come from GitHub's
   "Managing a custom domain for your GitHub Pages site" docs (checked 2026-11-10); recheck them there.
   - Apex domain (`archlens.sh`), `A` records:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - Apex domain, `AAAA` records (optional, IPv6):
     `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`
   - `www` subdomain: a `CNAME` record pointing to `tushar-mahalya.github.io`
     (without the repository name). With both set up, GitHub redirects between them.
4. When the DNS check passes in **Settings → Pages**, turn on **Enforce HTTPS**.
   The option can take up to 24 hours to appear.
5. Replace `https://tushar-mahalya.github.io/archlens/` with the new URL in every line marked
   `site-url` (`grep -rn site-url site/`):
   - `site/index.html`: canonical link, `og:url`, `og:image`, `twitter:image`, and the `"url"`
     in the `SoftwareApplication` JSON-LD
   - `site/sitemap.xml`: `<loc>`
   - `site/robots.txt`: `Sitemap:` line
6. Update the links outside `site/`: the "Website" link in `README.md`, and the website field in
   the repository's **About** settings.
7. Check the result: open the new URL, a missing page (for the 404 sheet), and the share preview
   (for example with a social card validator).
8. Add the new URL as a new property in Google Search Console and Bing Webmaster Tools
   (see below), and submit its `sitemap.xml` again.

## Option B: free, `https://<name>.pages.dev` on Cloudflare Pages

In the Cloudflare dashboard, create a Pages project connected to this repository, with
production branch `main`, no build command, and build output directory `site`. Pick a project
name that is still free, such as `archlens-docs`. The site is then served at a domain root with
HTTPS and a CDN, and robots.txt starts to work. Then do steps 5 to 7 above with the new URL,
and keep or remove the GitHub Pages workflow.

## Names that are already taken (checked 10 November 2026)

Other, unrelated projects use the name: the GitHub organization `archlens` (so `archlens.github.io`
is not available), `archlens.dev`, `archlens.io`, `archlens.app`, `archlens.pages.dev`,
`archlens.netlify.app`, and `archlens.vercel.app`. `archlens.sh` had no registration record.
Because of this, page titles, descriptions, and `llms.txt` lead with descriptive keywords
("living architecture docs for Claude Code") so search engines and agents can tell the projects apart.

## Get the current URL indexed

`robots.txt` only takes effect at a host root. On the current project-path URL
(`https://tushar-mahalya.github.io/archlens/`) search engines ignore `site/robots.txt` and do
not find `sitemap.xml` through it, so submit the sitemap by hand.

Google Search Console:

1. Open Search Console and add a property of type **URL prefix** with
   `https://tushar-mahalya.github.io/archlens/` (a Domain property needs DNS access, which
   `github.io` does not give you).
2. Choose the **HTML tag** verification method and copy the
   `<meta name="google-site-verification" content="...">` tag.
3. Paste it in `site/index.html` where the commented placeholder says
   "Search Console: paste the HTML-tag verification here", inside `<head>`. Remove the
   comment markers around it, commit, and wait for the Pages deployment.
4. Click **Verify**. Keep the tag in place; removing it un-verifies the property.
5. Open **Sitemaps**, enter `https://tushar-mahalya.github.io/archlens/sitemap.xml`, and submit.
   Optionally use **URL inspection → Request indexing** for the home page.

Bing Webmaster Tools: sign in and choose **Import from Google Search Console**. It imports the
verified site and its sitemap, so Bing needs no extra tag.

## Notes

- `robots.txt` allows all crawlers, including AI search and agent crawlers. It takes effect
  once the site is served from a host root.
- `llms.txt` and `llms-full.txt` summarize the project for agents. They use GitHub links only,
  so they do not change with the domain.
- `404.html` finds the site root at runtime (`/archlens/` or `/`). If the site ever moves to
  another sub-path, update the pattern in its first `<script>`.
