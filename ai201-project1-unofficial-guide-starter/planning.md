# Project 1 Planning: The Unofficial Guide

---

## Domain

The domain is reviews for budget smartphones that are $300 or less

This guide will make it easier for users to find a perfect smartphone in their budget. It will be based on public user reviews and coments, as well as professional reviews and tests. Typically, anyone who wanted to access this information would need to browse multiple websites and blindly trust random opinions in the internet, which makes it harder to make an informed decision on their smartphone. The guide gives them the information needed to make their next purchase.

---

## Documents

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

---

## Retrieval Approach

**Embedding model:** all-MiniLM-L6-v2

**Top-k:** 4

**Production tradeoff reflection:** A different model, such as an online model, would marginally improve accuracy and context, however wouldnt help us enough as our text is small. It would also have higher latency as it would not run locally.

---

## Evaluation Plan

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | What phones under $300 have the longest battery life in testing? | The Moto G at 19 hours |
| 2 | What phones under $300 have the best camera? | Pixel 9a for photography/software processing; CMF Phone 2 Pro for its 50MP telephoto |
| 3 | Does the CMF Phone 2 / Pixel 9a have overheating issues? | Pixel 9a: yes, owners report it gets warm even just browsing Chrome. CMF Phone 2 Pro: no notable overheating reported |
| 4 | What downsides do reviewers report about the CMF Phone 2 / Pixel 9a? | CMF Phone 2 Pro: no charger in box, only IP54, weak speaker, no eSIM. Pixel 9a: large bezels, thermal warmth, performance complaints |
| 5 | How many updates does the CMF Phone 2 / Pixel 9a get? | CMF Phone 2 Pro: 3 major OS updates. Pixel 9a: seven years of updates. |

---

## Anticipated Challenges

1. The user reviews are very noisy and contradictory, so it might have issues with choosing which to choose in answering a user's questions.

2. There are more sources about the two phones (Pixel 9A and the CMF Phone 2) than the ones listed in the compact budget phone guides, so it might be more biased.

---

## Architecture

[0] documents/ (.html/.txt/.pdf)
        |
        v
[1] Ingestion - pdfplumber / file read, strip HTML
        |
        v
[2] Chunking -  fixed 600-char chunking, 20% overlap
        |
        v
[3] Embedding + Store - all-MiniLM-L6-v2 (sentence-transformers) -> ChromaDB
        |
        v
[4] Retrieval - query embedding -> Chroma top-k=4 similarity search
        |
        v
[5] Generation - Groq LLM + grounding prompt -> answer w/ sources
        |
        v
[6] Interface (Streamlit)


---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:** Using Claude, i will provide the Chunking Strategy section and ask it to implement chunk_text() with fixed chunking and a 20% overlap, I will verifiy it by printing the chunk count and ensuring that the chunking algorithim does not split sentences.

**Milestone 4 — Embedding and retrieval:** I'll provide Claude my Retrieval Approach section and ask it to embed chunks with my provided model and store them in ChromaDB, as well as a top-k query function. I will verify this by querying my questions and checking if the returned chunks are on-topic.

**Milestone 5 — Generation and interface:** Using Claude, I will provide my grounding requirements: answer only from the retrieved chunks, refusing if the context does not contain the answer, and cite the source of each claim. I will ask it to write the Groq prompt that formats the top-k=4 chunks into the context and enforces those rules, plus a Streamlit interface with a query box that displays the answer and its cited sources. I will verify by running my 5 evaluation questions and confirming sources appear, and by asking an out-of-domain question (unrelated to phones or a flagship smartphone) to confirm it refuses instead of hallucinating.
