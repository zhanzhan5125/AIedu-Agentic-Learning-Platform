# Grading evaluation v3

`grading.json` is the expanded AI grading ablation dataset.

- 20 submissions and 60 answers.
- 25 short-answer, 15 programming, 10 single-choice, and 10 multiple-choice answers.
- The original v2 set is retained as the first 30 answers for comparability.
- The additional 30 answers emphasize partial credit, contradictory explanations,
  undefined behavior, memory ownership, integer conversion, I/O errors, and
  program boundary conditions.
- Every answer has a manually reviewed gold score, an accepted interval, and a
  review flag. The data is synthetic and contains no student identity data.

Run the formal suite with:

```powershell
uv run python -m scripts.evaluate_agents --suite grading --dataset-version v3 --output evals/results --seed 42
```

Every submission receives exactly one Reflection call; the complex-risk labels
only tell that reviewer what to focus on. Reflection is not considered useful
merely because it ran. The report compares
raw and reflected normalized MAE, accepted-range accuracy, score repairs,
regressions, validation defects, latency, and token usage.
