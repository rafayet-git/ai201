# The Unofficial Guide — Project 1

A retrieval-augmented guide to **budget smartphones (under ~$300)**.

**Run it:**
```bash
pip install -r requirements.txt
python ingest.py          # PDFs -> cleaned text -> chunks
python embed.py --rebuild # chunks -> embeddings -> ChromaDB
streamlit run app.py      # query interface
```

---

## Domain

**Budget smartphone recommendations (phones roughly under $300).**

This guide will make it easier for users to find a perfect smartphone in their budget. It will be based on public user reviews and coments, as well as professional reviews and tests. Typically, anyone who wanted to access this information would need to browse multiple websites and blindly trust random opinions in the internet, which makes it harder to make an informed decision on their smartphone. The guide gives them the information needed to make their next purchase.

---

## Document Sources

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | Best entry-level smartphones guide | Buyer's guide | https://www.gsmarena.com/best_entry_level_smartphones_buyers_guide-review-2034.php |
| 2 | Nothing CMF Phone 2 review | Pro review | https://www.gsmarena.com/nothing_cmf_phone_2_pro-review-2827.php |
| 3 | Nothing CMF Phone 2 review user comments | User reviews | https://www.gsmarena.com/nothing_cmf_phone_2_pro_5g-reviews-13821.php |
| 4 | Pixel 9a review | Pro review | https://www.gsmarena.com/google_pixel_9a-review-2825.php |
| 5 | Pixel 9a user comments | User reviews | https://www.gsmarena.com/google_pixel_9a-reviews-13478.php |
| 6 | Nothing CMF Phone 2 review from PhoneArena | Pro review | https://www.phonearena.com/reviews/cmf-phone-2-pro-review_id7240 |
| 7 | Budget and affordable phones | Buyer's guide | https://www.phonearena.com/news/Budget-affordable-cheap-low-cost-smartphones-android-this-year_id58696 |
| 8 | Best cheap phones | Buyer's guide | https://www.tomsguide.com/best-picks/best-cheap-phones |
| 9 | Best phones under $300 | Buyer's guide | https://www.androidcentral.com/best-android-phones-under-300 |
| 10 | Best phones under $300 in 2026 | Buyer's guide | https://www.techtimes.com/articles/313609/20251225/best-smartphones-buy-under-300-2026.htm |

---

## Chunking Strategy
**Chunk size:** ~600 characters, line-aware

**Overlap:** 20% of chunk size

**Reasoning:** I originally planned paragraph-based semantic chunking (as we mainly had articles with large paragraphs with different topics), but PDF extraction produces no paragraph breaks, as each line visually is on a separate line when extracted. So instead the pipeline packs multiple lines into chunks up to a 600-character cap, without ever splitting a line mid-word. This keeps individual opinions and review sentences intact.The 20% overlap carries context across boundaries so a fact spanning two chunks still appears whole.

**Final chunk count:** 387 chunks.

---

## Embedding Model

**Embedding model:** all-MiniLM-L6-v2

**Production tradeoff reflection:** A different model, such as an online model, would marginally improve accuracy and context, however wouldnt help us enough as our text is small. It would also have higher latency as it would not run locally.

---

## Grounded Generation

**System prompt grounding instruction:**

> You are an assistant that answers questions about budget smartphones using ONLY the reference
> documents provided in the user message. Follow these rules:
> 1. Use only facts found in the provided documents. Do not use any outside or prior knowledge.
> 2. If the documents do not contain enough information to answer, reply exactly: "I don't have enough information on that. Can you ask something else?"
> 3. Do not invent specs, numbers, or opinions that are not in the documents.
> 4. When you state a fact, mention which document number ([1], [2], …) it came from.

**How source attribution is surfaced:** The sources list returned by `ask()` is built from the metadata of the chunks actually retrieved and used in the response. The model also mentions exactly where each source is used wuth brackets `[1]/[2]`. Links of each document are listed in documents/sources.json

---

## Evaluation Report

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What phones under $300 have the longest battery life in testing? | Moto G ~19 hours | Moto G 2026 at 19h 10m; Phone 4a Pro past 18h. Noted prices weren't stated in context. Cited Tom's Guide. | Relevant | Accurate |
| 2 | What phones under $300 have the best camera? | Pixel 9a (photography/software); CMF Phone 2 Pro (50MP telephoto) | Refused | Partially relevant | Inaccurate |
| 3 | Does the CMF Phone 2 / Pixel 9a have overheating issues? | Pixel 9a: owners report it gets warm; CMF: no notable issues | Said neither overheats; both manage heat well. Cited the pro-review software/performance pages. | Relevant | Partially accurate |
| 4 | What downsides do reviewers report about the CMF Phone 2 / Pixel 9a? | CMF: no charger, IP54, weak speaker, no eSIM. Pixel: bezels, warmth, performance | Strong CMF list (design/screws/lint, one weak speaker, gimmicky lenses). Said Pixel not mentioned in context. | Partially relevant | Partially accurate |
| 5 | How many years of security updates does the CMF Phone 2 / Pixel 9a get? | CMF: 3 major OS updates; Pixel: 7 years | Refused | Partially relevant | Inaccurate |

**Retrieval quality:** 2 Relevant, 3 Partially Relevant, 

**Response accuracy:** 1 Accurate, 2 Partially Accurate, 1 Inaccurate

---

## Failure Case Analysis

**Question that failed:** Q5 — "How many years of security updates does the CMF Phone 2 / Pixel 9a get?"

**What the system returned:** "I don't have enough information on that. Can you ask something
else?" 

**Root cause (tied to a specific pipeline stage):** The retrieval/querying stage where the model selects the top K chunks. It seems that it recieved chunks that were about updates, but not the specific one that answered the question. It is possible that the prompt is misworded, as "years" and "security" are not included in the relevant documents.

**What you would change to fix it:** I can try to retrieve more chunks by increasing the value of k, or I can increase the relevance threshold so that the chunk with the valid information is more likely to be accepted.

---

## Spec Reflection

**One way the spec helped you during implementation:** It helped me in the chunking strategy, because I originally wated to implement semantic chunking sizes based on paragraph. However, since the data was retrieved via PDF's using pdfplumber, the formatting ended up being completely different from what I expected. As such, I resorted to a fixed-size chunking based on sentences, limited to 600 characters.

**One way your implementation diverged from the spec, and why:** I changed how the chunks were filtered during the retrieval stage, by adding a cosine-distance relevance filter (> 0.65 dropped) that refuses a prompt when nothing relevant is retrieved. I added it because the prompt alone didn't reliably refuse out-of-domain questions. 

---

## AI Usage

**Instance 1**

- *What I gave the AI:* My Chunking Strategy section from `planning.md` and the pipeline diagram, and asked it to implement `chunk_text()`.
- *What it produced:* A function that split on blank-line paragraph boundaries and packed paragraphs up to a size cap with overlap, including sanitization of the raw text.
- *What I changed or overrode:* I inspected the output and noticed the chunks were all nearly the same size and included varying topics in one chunk. I directed the AI to diagnose it, and we found that the raw text had zero blank-line breaks, so the "paragraph" split produced one giant block that fell through to a blind character splitter. I overrode the plan by switching to line-based fixed-size chunking at 600 characters, then updated `planning.md` to document why the original plan did not work.

**Instance 2**

- *What I gave the AI:* A request to store the sources/citations in each chunk by storing the source URL as metadata.
- *What it produced:* Code that harvested the URL from the PDF page header via regex.
- *What I changed or overrode:* I spotted that many stored URLs ended in `...`, which meant that the browser was truncating long URL's and not getting the full URL link. To fix this, I decided to include a `sources.json` inside the documents folder, which listed every file name along with its source URL. The AI suggested renaming the files or hardcoding the URL's inside the code, but I rejected these for ease of use.
