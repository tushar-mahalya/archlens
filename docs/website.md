# Project website

The website is the static `site/` folder: HTML, CSS, and dependency-free JavaScript.
`index.html` is the landing page and `docs/index.html` is the guide. `main.js` holds the shared
behavior, and `lab.js` holds the interactive examples and the in-view illustrations.
The examples replay recorded output of `archlens.py`. When output changes, record it again:
the verdicts in `lab.js` come from `status` on the order example, and the query results come
from `query` on this repository.
It is served at **https://archlens-docs.pages.dev/** from Cloudflare Pages (project `archlens-docs`).
It is the only address; GitHub Pages is turned off for this repository.

## How it deploys

The [Cloudflare Pages workflow](../.github/workflows/cloudflare-pages.yml) runs on every push to `main`
that changes `site/`, and on demand. It uploads `site/` with a pinned Wrangler version.

It needs two repository secrets. Without them it skips with a notice.

1. `CLOUDFLARE_ACCOUNT_ID`: the account ID that `npx wrangler@4.159.0 whoami` prints.
2. `CLOUDFLARE_API_TOKEN`: in the Cloudflare dashboard, open **My Profile → API Tokens →
   Create Token → Create Custom Token**, give it the account permission **Pages Write** (older
   dashboards call it **Cloudflare Pages → Edit**), and create it. Store it without echoing it:
   `gh secret set CLOUDFLARE_API_TOKEN` (the command prompts for the value).

To deploy by hand, run from the repository root after `npx wrangler@4.159.0 login`:

```text
npx wrangler@4.159.0 pages deploy site --project-name archlens-docs --branch main
```

`site/_headers` sets security and cache headers on Cloudflare Pages.

## Absolute URLs

Internal links, assets, and scripts are relative. Only these lines hold the site URL; change all
of them if the site moves, for example to a custom domain:

- `site/index.html`: lines marked `site-url` (canonical, `og:url`, `og:image`, `twitter:image`)
  and the `url` in the `SoftwareApplication` JSON-LD.
- `site/docs/index.html`: the lines marked `site-url`.
- `site/sitemap.xml` (`<loc>`) and `site/robots.txt` (`Sitemap:`).
- `README.md` (Website link) and the repository's website field (`gh repo edit --homepage <url>`).

A custom domain can be added later in **Workers & Pages → archlens-docs → Custom domains**.
`archlens.sh` had no registration record on 10 November 2026.

## Search engines and agents

- `robots.txt` allows every crawler, including AI search and agent crawlers, and lists the sitemap.
- `llms.txt` and `llms-full.txt` give agents a short and a full plain-text summary.
- The page has `SoftwareApplication` and `FAQPage` structured data.
- **IndexNow** (Bing, Yandex, Seznam, Naver, and others): the key file is
  `site/af83e24b5969ec49b7603348dc2605b2.txt`. After a deployment that changes content, notify them:

  ```text
  curl "https://api.indexnow.org/indexnow?url=https://archlens-docs.pages.dev/&key=af83e24b5969ec49b7603348dc2605b2"
  ```

- **Google** does not support IndexNow. The site is verified in Google Search Console as a
  **URL prefix** property for `https://archlens-docs.pages.dev/`, with the HTML file
  `site/google4dcafa1fef06d189.html`. `site/_redirects` serves it at its exact URL, because
  Cloudflare Pages otherwise redirects `.html` URLs. Keep the file byte-exact and deployed;
  removing it un-verifies the property. The sitemap to submit is `https://archlens-docs.pages.dev/sitemap.xml`.
- **Bing Webmaster Tools** can import the verified site from Search Console.

## Names that are already taken (checked 10 November 2026)

Other, unrelated projects use the name: the GitHub organization `archlens` (so `archlens.github.io`
is not available), `archlens.dev`, `archlens.io`, `archlens.app`, `archlens.pages.dev`,
`archlens.netlify.app`, and `archlens.vercel.app`. Page titles, descriptions, and `llms.txt` therefore
lead with descriptive keywords ("living architecture docs for Claude Code"), and `llms.txt` states
that this project is unrelated to the others, so search engines and agents can tell them apart.

## Checks before publishing

- `node --check site/main.js` and `node --check site/lab.js`
- Serve `site/` locally (`python3 -m http.server` inside it) and check both themes at desktop and
  360 px width, with and without reduced motion.
- Every `href="#..."` target exists, and every local asset returns 200.
- Click every example: the five edits, the three queries, the quiz, and the 0.4.0 and 0.5.0 switch.
- With JavaScript off, the page still shows the static content and no dead controls.
