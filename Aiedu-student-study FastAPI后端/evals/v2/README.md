# v2 evaluation data

v2 keeps the v1 questions and grading/routing labels, but remaps RAG evidence after the structure-aware reindex.

- All v1 evidence references were snapshotted before reindexing; the reviewed v2 set contains 43 references for the same 40 questions.
- High-overlap references were remapped automatically and then reviewed against the question and new chunk text.
- Chapter-overview cases now reference generated `section_index` blocks instead of noisy table-of-contents pages.
- Cases whose former large chunk mixed teaching content with ideological examples were manually changed to the chapter objective or section index that directly answers the question.
- `rag-004`, `rag-010`, and `rag-028` include additional valid evidence chunks so alternative relevant passages are not counted as false negatives.
- The active corpus contains 597 chunks after reindexing: 549 textbook chunks and 48 syllabus chunks, including 17 chapter-level `section_index` chunks.
- PDF sections retain an 80-token overlap across page boundaries. Retrieval keeps the ranked chunk identity stable, while production citations may attach complete neighbouring sentences for readability.

The source questions remain unchanged, so v1 and v2 compare ingestion/retrieval changes rather than a new query distribution. Raw content hashes necessarily differ because cleaning and structural chunking changed the chunk boundaries.
