# Why the performance result changed

On 7 October 2026, the same current reader and timing code was measured against PostgreSQL for the IT role at three dataset sizes. Each case used three warm-ups and ten timed repetitions. Dataset changes were rolled back; PostgreSQL still contains 10,000 rows afterward.

| Total rows | PostgreSQL average ms | Python reader average ms | PostgreSQL / reader |
|---|---|---|---|
| 10 | 0.237 | 0.057 | 4.167 |
| 1,000 | 0.546 | 1.709 | 0.320 |
| 10,000 | 3.228 | 16.982 | 0.190 |

These diagnostic measurements are separate from the 27-case submission suite. They reproduce both outcomes without changing the reader algorithm: Python wins on the tiny demo; PostgreSQL wins on larger datasets.

The Python path opens a local file and loops through every row, decoding four fields and applying a predicate. Its work grows with the dataset. The PostgreSQL path has a fixed client/query overhead, but its engine handles larger scans efficiently. At ten rows the reader has little work and avoids the query round trip. At thousands of rows, its Python loop costs more.

The prior committed benchmark already excluded connection setup and policy extraction. The current benchmark does too. Full-row correctness comparison, fresh export and table locking are outside both timed regions, so adding these checks did not directly add that work to the reported scan latency. AST validation happens once at the start of each reader call; it does not validate the entire tree separately for each row.

This experiment identifies dataset size as a sufficient explanation for the reversal. It does not establish the exact cause of any earlier unsaved timing result, and cache state, policy complexity and machine load can also affect measurements.

Current data flow: synthetic employees are inserted into PostgreSQL, PostgreSQL exports the binary snapshot, and Python filters that export. A comparison-summary CSV contains timings, counts, policy and correctness, not employee records.
