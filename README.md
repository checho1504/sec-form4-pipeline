# SEC Form 4 to R2 Parquet Pipeline

This pipeline watches SEC EDGAR for new Form 4 filings (those are the
filings that show when a company insider buys or sells stock). Whenever it
finds one it hasn't seen before, it grabs the transaction details and adds
them to a Parquet file sitting in Cloudflare R2. It also keeps a memory of
what it's already looked at, so it never repeats itself, whether that's an
hour from now or six months from now on a computer you haven't even bought
yet.

## The basic idea

```
GitHub Actions schedule
      ↓
Run main.py automatically
      ↓
Fetch new SEC Form 4 filings   (EDGAR "current filings" Atom feed)
      ↓
Skip already processed accessions   (state.json in R2)
      ↓
Parse useful rows   (issuer, owner, transaction code, shares, price, ...)
      ↓
Update Parquet in R2   (download, combine, dedupe, re upload)
      ↓
Save pipeline memory back to R2   (state.json)
```

Nothing lives on your laptop, and nothing lives in the GitHub repo either.
GitHub Actions just runs the script on a timer, and R2 is where all the
actual data and the "what have I already seen" memory hang out.

## 1. Spin up an R2 bucket

Head into the Cloudflare dashboard, then R2, then Create bucket. Give it a
name you'll actually recognize later. While you're there, grab your
Cloudflare Account ID too, you'll need it in a second.

## 2. Make yourself an R2 API token

Still in R2, go to Manage R2 API Tokens, then Create API Token. Give it read
and write access on the bucket you just made. Cloudflare will hand you an
Access Key ID and a Secret Access Key. Copy both somewhere safe, especially
the secret key, since it only shows up once.

## 3. Tell GitHub your secrets

Over in your repo, go to Settings, then Secrets and variables, then Actions,
then New repository secret. Add each of these one at a time:

| Secret name             | Value                                      |
|--------------------------|---------------------------------------------|
| `R2_ACCOUNT_ID`          | Your Cloudflare account ID                 |
| `R2_ACCESS_KEY_ID`       | From the R2 API token                      |
| `R2_SECRET_ACCESS_KEY`   | From the R2 API token                      |
| `R2_BUCKET`              | Your bucket name                           |
| `SEC_USER_AGENT`         | e.g. `"Jane Doe jane@example.com"`         |

That last one really matters. SEC checks for a real User Agent (your name
and an email) on every request, and it will block you if that's missing or
looks fake. There's more on that here if you're curious:
https://www.sec.gov/os/webmaster-faq#developers

## 4. Get the files into your repo

You just need these three:

```
main.py
requirements.txt
.github/workflows/sec-form4-pipeline.yml
```

Once they're pushed, the workflow takes over from there. It runs every 30
minutes during market hours on weekdays (`*/30 13-21 * * 1-5` UTC), and you
can also kick it off manually any time from the Actions tab.

## 5. Make sure it actually works

Go to the Actions tab, click SEC Form 4 Pipeline, then Run workflow, and
watch the logs come in. The very first run won't have any memory yet, so
it'll work through a batch of recent filings (up to `MAX_FILINGS_PER_RUN`,
100 by default) and create two new things in your bucket: `sec_form4/state.json`
and `sec_form4/form4_transactions.parquet`.

If those show up, you're good. It'll just keep running on its own from here.

## Things worth knowing, and maybe tweaking later

**Where the filings come from.** It's pulling from EDGAR's `getcurrent`
feed, which only shows recent activity. That's fine if the pipeline is
running every 15 to 30 minutes like clockwork, but if it ever goes quiet for
a long stretch, some filings could scroll off the feed before it catches
them. If you want zero gaps instead of "good enough," the SEC's full text
search API or the daily index files are the sturdier option (the search API
lives at efts.sec.gov/LATEST/search-index, with forms=4 as a filter). Just
say the word and I'll wire that in instead.

**Picking the right XML file.** Filers don't name their files consistently,
so `get_filing_xml_url` is doing a bit of educated guessing, looking for
"primary" or "form4" somewhere in the filename. Worth glancing at the
actual output early on just to make sure it's not quietly missing anything.

**What counts as a duplicate.** Rows get deduped using the accession number,
security title, transaction date, transaction code, and share count
together. Loosen or tighten that if it doesn't match how you think about
duplicates for your use case.

**Being polite to SEC's servers.** There's a small delay built in
(`SEC_REQUEST_DELAY_SECONDS`, 0.3 seconds by default) between requests so
the script isn't hammering EDGAR.

**Not tripping over itself.** The workflow has a concurrency guard built in,
so two runs can never overlap and corrupt the state file or the Parquet
file by writing to them at the same time.