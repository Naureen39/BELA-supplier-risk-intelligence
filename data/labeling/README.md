# Gold set annotation (Label Studio Community)

Two projects, configured by the XML files in this folder. Start Label Studio, create the projects,
paste the labeling configuration, and import tasks produced by `data/scripts/prepare_gold_tasks.py`.

| Project | Config | Target size | Notes |
|---|---|---|---|
| Structured records | `structured_config.xml` | 400 records, at least 100 hard cases | Regulator or filing record mapped to a canonical company or NIL |
| News mentions | `news_config.xml` | 200 mentions (150 English, 50 other) | Mention in a sentence mapped to a company or NIL |

Two annotators label a shared 20 percent subset. Compute Cohen's kappa with
`python -m data.scripts.gold_agreement a.jsonl b.jsonl`. Export final labels to
`data/gold/structured.jsonl` and `data/gold/news.jsonl`.

## Guidelines

1. Choose the canonical company that operates or owns the named entity at the record date.
2. A plant, facility, or branch name maps to its legal operating company, not to the ultimate parent,
   unless the record names the parent. Record the parent separately in the notes field.
3. If two candidates remain equally plausible after reading the context, choose NIL and set
   the "Ambiguous" flag. Do not guess.
4. Choose NIL when the entity is a government body, nonprofit, individual, product, or is absent from
   the candidate list and the web search confirms no match.
5. Same name in a different state or country is a different company. Check state and city.
6. Mark "Hard case" when: same name in different states, parent versus subsidiary, near-identical
   names, or plant-specific names.
7. Companies used in gold sets must not appear in training data (split by company).
8. Do not copy article text beyond the sentence shown. Record the source URL.
