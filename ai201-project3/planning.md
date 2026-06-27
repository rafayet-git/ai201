# TakeMeter — Planning

## Community

I chose **r/youtubedrama**, a subreddit where people discuss conflicts, controversies, and public fallouts involving online creators (YouTubers, streamers, podcasters). It's a strong fit for a discourse-quality classifier because the comment sections on a single drama thread span a huge range: some people dig up timelines and direct quotes ("receipts"), some deliver confident moral verdicts on a creator with nothing to back them up, and a large fraction are just jokes, snark, or emotional venting. That spread — evidence vs. assertion vs. reaction — is something regulars actively police ("source?", "this is just a hot take", "lol"), so the distinction is real to the community, not imposed from outside.


## Labels

My three labels are:

- **information** - A specific, checkable information about the drama: who is involved, what happened, a direct quote, a date, a named video/tweet/stream, a link, or a concrete sequence of events.
  - *Example 1:* "So far the following YouTubers are getting involved: Coffeezilla is starting an investigation, LegalEagle reached out to offer help, the Civil Rights Lawyer says he's on it."
  - *Example 2:* "In the video of Ben reading the email BAM sent out, he shows a clip of Asmongold, so he's already been talking about it."
- **opinion** - A judgment, prediction, or piece of reasoning stated without verifiable evidence. Covers both lazy verdicts and analysis that simply cites no sources.
  - *Example 1:* "Who would've guessed that the grifters who complain about free speech don't believe in it."
  - *Example 2:* "Challenging a strike opens you up to a lawsuit, and part of that is providing your real address so you can be served — is it worth handing your info to the opposing party?"
- **reaction** - A comedic, expressive, or emotional response with no checkable fact and no real argument: memes, riffs, one-liners, shock, jokes. Common and often elaborate in this community.

## Hard edge cases

- **Elaborate joke that looks substantive** — long, clever comments that are pure comedy (the multi-paragraph Dr. Doom / MCU-villain analogy thread). Length and effort make them *look* like analysis.
  > **Decision rule:** Tone and intent decide, not length. If the point is the bit/the laugh and you can't extract a checkable fact or a serious claim, it's `reaction` no matter how long it is.

- **Info wrapped in a joke** — e.g. *"Asmon just dropped a 2 hour video, lmao."* Joke tone (→ `reaction`) but carries a concrete, checkable fact (→ `info`).
  > **Decision rule:** `info` wins whenever a specific verifiable fact is present, regardless of tone.
  > The "lmao" doesn't downgrade it; the fact (Asmon released a 2hr video) is the content.

- **The "one decorative stat" opinion** — a comment that drops a vague number to sound credible but isn't reasoning from it, e.g. *"He's lost like 200k subs, dude is finished."*
  > **Decision rule:** This is `opinion`, not `info`. `info` requires the fact to be *specific and checkable* and to be the substance of the comment. A lone round number that's just flavor for a verdict ("finished") doesn't qualify — strip the opinion and nothing verifiable remains.

### Actual annotation decisions (encountered while labeling)

Three real comments that gave me genuine pause during annotation, and what I decided:

1. *"I think what people are missing is, even if it falls under fair use, challenging a strike opens up a lawsuit and part of that is providing your real address so you can be served…"* — `information` vs `opinion`. Reads like analysis, but states a checkable procedural fact about how copyright strikes work. **Decided `information`** (substance is a verifiable claim, not a verdict on a person).
2. *"God this situation is so messy, all they had to do was hand the collection back. But a CEO is gonna CEO 🤷‍♂️"* — `opinion` vs `reaction`. A faint opinion ("all they had to do"), but the dominant register is emotional venting + a meme construction. **Decided `reaction`.**
3. *"I'm not sure if anyone has mentioned this but where's the arbitration clause and why hasn't it been triggered?"* — `opinion` vs `reaction`. A rhetorical question implying a critique but asserting no checkable fact and making no real argument. **Decided `reaction`** — closest call in the set, and a real annotation-consistency risk.

## Data collection plan

- **Source:** Examples are collected from Reddit's public `.json` endpoints (no API key needed) — append `.json` to any thread.
  - The URl to download the top 100 posts: `https://www.reddit.com/r/youtubedrama/top.json?t=year&limit=100`
  - The URL to download a specific thread's comments: `https://www.reddit.com/r/youtubedrama/comments/<post_id>.json`
- **Method:** `parse.py` recursively walks each thread's comment tree, filters to comments with 5–400 words (drops bot/automod/deleted/`[removed]`), dedupes, and writes `data/raw_comments.csv` for manual labeling. 
- **Target:** 200 or more labeled examples, aiming for around 20% per label.
- **If a label is underrepresented after 200:** dump 1–2 more threads that relate to the specific label, or selectively label posts to reduce the heaviest label.

## Evaluation metrics

I'll report:
- **Overall accuracy** (headline, both models).
- **Per-class precision, recall, and F1 + macro-F1** — macro-F1 weights each class equally, so failure on sparse labels actually shows up. This is the metric I optimize for.
- **3×3 confusion matrix** — to see *which* confusions happen (I expect `info`↔`opinion` to be the hard boundary, mirroring my edge cases).
- **Error analysis** on ≥3 specific misclassifications.

## Definition of success

- **Baseline to beat:** majority-class accuracy, and the Groq zero-shot llama-3.3-70b baseline.
- **Good enough:** fine-tuned model **macro-F1 ≥ 0.65** and **`info` recall ≥ 0.55** (catching the evidence-bearing comments is the point of the tool), while beating the zero-shot baseline's macro-F1.
- **Genuinely useful for a real community tool** (e.g. surfacing high-information comments): macro-F1 ≥ 0.75 with no class's F1 below 0.6. A subjective task like this likely lands between "good enough" and "useful," and the error analysis matters more than the headline number.

## AI Tool Plan

This project has little code to generate, so AI tools help at three points:

1. **Label stress-testing (before annotating):** I'll give Claude my three definitions + the decision order and ask it to generate 8–10 comments that sit on the `info`↔`opinion` and `reaction`↔`info` boundaries. Any I can't classify cleanly means a definition needs tightening
2. **Annotation assistance:** I'll use Groq (llama-3.3-70b) to pre-label the raw batch, then review every label myself (the model's guess is a suggestion, not ground truth). I'll keep a `prelabel` column recording the model's guess alongside my final label so I can (a) disclose which were pre-labeled in the AI usage section and (b) measure my own override rate. *Note: this Groq pre-labeling is separate from the zero-shot baseline, which runs only on the held-out test set.*
3. **Failure analysis:** After evaluation I'll hand the list of wrong predictions (text + true label + predicted label) to an AI tool and ask it to cluster the errors into patterns. I'll then verify each proposed pattern by reading the actual comments before putting it in the report — the AI proposes hypotheses, I confirm them against the data.
